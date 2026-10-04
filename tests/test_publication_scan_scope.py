from unittest.mock import Mock, patch
import pytest
from deals import deal_engine as engine


def test_manual_analysis_does_not_claim_a_pipeline_batch():
    with patch.object(engine,"sb_upsert") as upsert:
        assert engine.register_publication_scan("") is None
    upsert.assert_not_called()


def test_batch_registration_keeps_exact_pipeline_start_timestamp():
    started="2026-10-04T17:53:03.123456+00:00"
    with patch.object(engine,"sb_upsert") as upsert:
        assert engine.register_publication_scan(started)==started
    assert upsert.call_args.args==( "publication_scan_batches", {"started_at":started}, "started_at")


@pytest.mark.parametrize("started",["bad","2026-10-04T17:53:03"])
def test_invalid_or_ambiguous_start_is_rejected(started):
    with pytest.raises(ValueError):
        engine.register_publication_scan(started)


def test_completion_uses_service_rpc_and_exact_batch_identity():
    started="2026-10-04T17:53:03.123456+00:00"
    import json
    with patch.object(engine,"headers",return_value={}),patch.object(engine,"urlopen") as request:
        engine.complete_publication_scan(started)
    req=request.call_args.args[0]
    assert req.full_url.endswith("/rpc/complete_publication_scan")
    assert json.loads(req.data)=={"p_started_at":started}
