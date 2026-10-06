from datetime import datetime,timezone
from unittest.mock import Mock,patch
import threading,time
from collectors import n11
from collectors.deal_competitor_batch import fresh_competitor_pairs
from collectors import amazon_competitors as competitors
from deals import refresh_competitor_offers as refresh

CUT=datetime(2026,10,5,tzinfo=timezone.utc)
def data():
 seed={'source_store':'amazon','asin':'A','title':'ACME X123 Black Headphones','brand':'ACME'}
 offers=[{'merchant_id':m,'merchant_product_id':i,'product_variant_id':v,'price':100,'in_stock':True,'last_checked_at':'2026-10-05T10:00:00Z'} for m,i,v in [('a','A','va'),('n','N','vn')]]
 variants=[{'id':'va','product_id':'pa'},{'id':'vn','product_id':'pn'}]
 products=[{'id':p,'title':seed['title'],'brand':'ACME'} for p in ['pa','pn']]
 matches=[{'product_id':p,'canonical_product_id':'canonical','status':'approved'} for p in ['pa','pn']]
 merchants=[{'id':'a','slug':'amazon'},{'id':'n','slug':'n11'}]
 return seed,offers,variants,products,matches,merchants

def test_fresh_rival_skips_search_only_with_approved_same_product_evidence():
 seed,offers,variants,products,matches,merchants=data()
 with patch.object(competitors,'same_product',wraps=competitors.same_product):
  assert fresh_competitor_pairs([seed],offers,variants,products,matches,merchants,CUT)=={('amazon','A','n11')}
 for broken in ['stale','stock','unapproved','model']:
  seed,offers,variants,products,matches,merchants=data()
  if broken=='stale':offers[1]['last_checked_at']='2026-10-04T10:00:00Z'
  if broken=='stock':offers[1]['in_stock']=False
  if broken=='unapproved':matches[1]['status']='pending'
  if broken=='model':products[1]['title']='ACME X999 Black Headphones'
  assert fresh_competitor_pairs([seed],offers,variants,products,matches,merchants,CUT)==set()

def test_same_queries_are_deduplicated_but_different_variants_still_search():
 seed,*_=data();other=dict(seed,asin='B');different=dict(seed,asin='C',title='ACME X123 White Headphones')
 with patch.object(competitors,'_search_job',return_value={'status':'unverified'}) as job:
  rows=competitors.discover_competitors([seed,other,different],deduplicate=True,fresh_pairs={('amazon','A','n11')})
 assert job.call_count==10
 assert sum(row.get('reason')=='same-query-in-batch' for row in rows)==4
 assert sum(row.get('reason')=='fresh-approved-offer' for row in rows)==1

def test_refresh_streams_are_serial_per_merchant_and_globally_capped():
 lock=threading.Lock();active=set();peak=0
 def one(session,target,slug,cutoff,apply):
  nonlocal peak
  with lock:
   assert slug not in active
   active.add(slug);peak=max(peak,len(active))
  time.sleep(.01)
  with lock:active.remove(slug)
  return {'price':100,'in_stock':True}
 targets=[{'id':str(i),'merchant_id':str(i%5)} for i in range(15)]
 with patch.object(refresh,'refresh_one',side_effect=one):
  assert refresh.refresh_targets(targets,{str(i):str(i) for i in range(5)},CUT,delay=0,workers=9)==(15,0)
 assert 1<peak<=3

def test_n11_batch_reads_and_unchanged_images_do_not_write():
 replies=[[{'id':'o','merchant_product_id':'sku','product_variant_id':'v'}],[{'id':'v','product_id':'p','image_url':'image'}],[{'id':'p','image_url':'image'}]]
 with patch.object(n11,'sb',side_effect=replies) as db:
  offers,variants,images=n11.existing_snapshots([{'merchant_product_id':'sku'}],'merchant')
 assert db.call_count==3
 with patch.object(n11,'sb') as db:
  n11.sync_existing_product_image('v','image',variants['v'],images)
 db.assert_not_called()
 with patch.object(n11,'sb') as db:
  n11.sync_existing_product_image('v','new-image',variants['v'],images)
 assert db.call_count==2
