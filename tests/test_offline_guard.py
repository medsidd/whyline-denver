import pytest
from google.cloud import bigquery, storage


def test_suite_cannot_create_cloud_clients():
    for client in (storage.Client, bigquery.Client):
        with pytest.raises(RuntimeError):
            client()
