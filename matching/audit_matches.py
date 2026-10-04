"""Offline catalog funnel analysis. Reads a JSON snapshot; never calls Supabase."""
import argparse
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path
import product_matcher as matcher
import apply_matches as writer


def rows_from_snapshot(data):
    products = {r['id']:r for r in data['products']}
    variants = {r['id']:r for r in data['product_variants']}
    merchants = {r['id']:r for r in data['merchants']}
    rows=[]
    for offer in data['offers']:
        variant=variants.get(offer.get('product_variant_id'))
        product=products.get(variant.get('product_id')) if variant else None
        merchant=merchants.get(offer.get('merchant_id'))
        if not product or not merchant or not offer.get('in_stock'):
            continue
        if product.get('active') is False or variant.get('active') is False:
            continue
        rows.append({**offer,'offer_id':offer['id'],'product_id':product['id'],
                     'variant_id':variant['id'],'title':product.get('title') or '',
                     'brand':product.get('brand'),'gtin':variant.get('gtin'),
                     'sku':variant.get('sku'),'merchant':merchant.get('name') or merchant.get('slug'),
                     'price':float(offer.get('price') or 0)})
    return rows


def price_gap_funnel(rows, matches):
    cids={r['product_id']:r['canonical_product_id'] for r in matches if r.get('status')=='approved'}
    grouped=defaultdict(dict)
    for row in rows:
        cid=cids.get(row['product_id'])
        if not cid or row['price']<=0:
            continue
        key=(cid,row.get('currency') or 'TRY')
        stores=grouped[key]
        stores[row['merchant_id']]=min(stores.get(row['merchant_id'],float('inf')),row['price'])
    result=Counter()
    for stores in grouped.values():
        prices=sorted(stores.values())
        if len(prices)<2:
            result['single_store']+=1
        else:
            result['cross_store']+=1
            if (prices[1]-prices[0])/prices[1]*100+1e-9 >= 15:
                result['gap_at_least_15_percent']+=1
            else:
                result['gap_below_15_percent']+=1
    return dict(result)


def project(rows, groups, matches, legacy=False):
    state=[dict(r) for r in matches]
    counts=Counter(); reasons=Counter(); examples=[]
    for n,(score,indexes,edges) in enumerate(groups):
        if legacy:
            if score < writer.AUTO_APPROVE_MIN:
                reasons['below-auto-approve']+=1;continue
            members=[rows[i] for i in indexes]
            bypid={x['product_id']:x for x in state}
            existing=[bypid[r['product_id']] for r in members if r['product_id'] in bypid]
            cids={r['canonical_product_id'] for r in existing}
            if len(cids)>1:
                reasons['canonical-conflict']+=1;continue
            new=[r for r in members if r['product_id'] not in bypid]
            if not new:
                reasons['already-linked']+=1;continue
            plan={'action':'attach' if cids else 'create','canonical_id':next(iter(cids),None),
                  'new_members':new,'score':score,'reason':','.join(sorted({e[1] for e in edges}))}
        else:
            plan=writer.plan_group(score,indexes,edges,rows,state)
            if plan['action'] not in {'create','attach'}:
                reasons[plan['reason']]+=1;continue
        cid=plan['canonical_id'] or 'projected:'+str(n)
        state.extend({'product_id':r['product_id'],'canonical_product_id':cid,'status':'approved'} for r in plan['new_members'])
        counts['new_canonicals']+=plan['action']=='create'
        counts['attached_groups']+=plan['action']=='attach'
        counts['new_product_matches']+=len(plan['new_members'])
        examples.append({'action':plan['action'],'score':round(plan['score'],2),'reason':plan['reason'],
                         'members':[{'merchant':rows[i]['merchant'],'title':rows[i]['title'],'brand':rows[i].get('brand'),
                                     'brand_source':rows[i].get('brand_source'),'product_id':rows[i]['product_id']} for i in indexes]})
    return {'counts':dict(counts),'skips':dict(reasons),'price_gap_funnel':price_gap_funnel(rows,state),'plans':examples}


def analyze(data, baseline=None):
    raw=rows_from_snapshot(data)
    rows=matcher.prepare_rows(raw)
    diagnostics=Counter(); inferred=Counter(); brandless=Counter(); bands=Counter()
    for r in raw:
        if not matcher.normalize_brand(r.get('brand')): brandless[r['merchant']]+=1
    for r in rows:
        if r.get('brand_source'): inferred[r['merchant']]+=1
    for i,j in matcher.candidate_pairs(rows):
        score,reason=matcher.pair_score(rows[i],rows[j])
        diagnostics[reason]+=1
        bands['auto' if score>=writer.AUTO_APPROVE_MIN else 'review' if score>=matcher.MIN_SCORE else 'rejected']+=1
    groups=matcher.build_groups(rows,min_score=writer.AUTO_APPROVE_MIN)
    report={'scope':'all active in-stock offers in the supplied snapshot; no freshness expansion in production',
            'snapshot_counts':{k:len(v) for k,v in data.items()},'active_offer_rows':len(rows),
            'missing_brand_by_merchant':dict(brandless),'inferred_brand_by_merchant':dict(inferred),
            'candidate_pair_reasons':dict(diagnostics),'candidate_pair_bands':dict(bands),
            'approved_groups_after':len(groups),'existing_price_gap_funnel':price_gap_funnel(rows,data['product_matches']),
            'after':project(rows,groups,data['product_matches']),
            'limitations':['Prices are snapshot prices, not live verified deals.',
                          'History verification and admin decisions are not simulated.',
                          'No rows are written to Supabase; counts are projected plans.',
                          'Real regression labels are title/model evidence; no product-detail-page verification.']}
    if baseline:
        oldgroups=baseline.build_groups(raw)
        report['candidate_groups_before']=len(oldgroups)
        report['approved_groups_before']=sum(s>=writer.AUTO_APPROVE_MIN for s,_,_ in oldgroups)
        report['before']=project(raw,oldgroups,data['product_matches'],legacy=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--since',help='Optional inclusive ISO-8601 last_checked_at filter')
    args=parser.parse_args()
    data=json.loads(args.snapshot.read_text(encoding='utf-8'))
    if args.since:
        from datetime import datetime
        since=datetime.fromisoformat(args.since.replace('Z','+00:00'))
        data['offers']=[r for r in data['offers'] if r.get('last_checked_at') and
                        datetime.fromisoformat(r['last_checked_at'].replace('Z','+00:00'))>=since]
    baseline=None
    if args.baseline:
        spec=importlib.util.spec_from_file_location('baseline_matcher',args.baseline)
        baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
        # Cache existing pure extractors only; preserve baseline matching semantics.
        from functools import lru_cache
        for name in ['normalize_text','normalize_brand','extract_volume_ml','extract_model_tokens','extract_age_ranges',
                     'extract_pack_counts','extract_weight_grams','extract_storage_gb','extract_ram_gb','extract_cpu_tokens',
                     'extract_screen_inches','extract_phone_family','generic_tech_family_keys','extract_critical_variant_suffixes',
                     'tech_model_keys','consumer_model_phrase','technology_profile']:
            setattr(baseline,name,lru_cache(maxsize=32768)(getattr(baseline,name)))
    report=analyze(data,baseline)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'before','after'}},ensure_ascii=False,indent=2))
    for label in ['before','after']:
        if label in report: print(label,json.dumps({k:v for k,v in report[label].items() if k!='plans'},ensure_ascii=False))


if __name__=='__main__':
    main()
