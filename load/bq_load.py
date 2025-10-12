"""Parametric BigQuery loader for WhyLine Denver raw datasets."""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import logging
import sys
import uuid
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from google.api_core.exceptions import NotFound
from google.cloud import bigquery, storage

from load.registry import JOBS, META_COLUMNS, JobSpec
from whylinedenver.config import settings

LOGGER = logging.getLogger("load.bq_load")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s [%(levelname)s] %(message)s")

RAW_ROOT_LOCAL = Path("data/raw")
RAW_ROOT_GCS = "raw"
INGESTION_LOG_TABLE = "__ingestion_log"


@dataclass
class FileRef:
    """Represents a single file candidate for loading."""

    source_path: str  # original path or gs:// URI
    relative_path: str
    extract_date: date | None
    size: int | None
    is_gcs: bool
    local_path: Path | None = None
    blob: storage.Blob | None = None


@dataclass
class PlanItem:
    """Plan entry describing whether to load or skip a file."""

    job: JobSpec
    file: FileRef
    hash_md5: str | None
    already_loaded: bool = False
    skip_reason: str | None = None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load raw WhyLine Denver datasets into BigQuery.")
    parser.add_argument(
        "--src", choices=("local", "gcs"), default="gcs", help="Input source location."
    )
    parser.add_argument(
        "--bucket", help="GCS bucket name (required for --src gcs, used for temp uploads)."
    )
    parser.add_argument("--since", help="Only load extracts on/after this YYYY-MM-DD date.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the load plan without running it."
    )
    parser.add_argument(
        "--max-files", type=int, help="Optional cap on the number of files to load."
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        since_date = date.fromisoformat(args.since) if args.since else None
    except ValueError as exc:
        raise SystemExit(f"--since must be YYYY-MM-DD: {exc}") from exc

    bucket = args.bucket
    if args.src == "gcs" and not bucket:
        raise SystemExit("--bucket is required when --src gcs")

    if args.src == "local" and not bucket:
        bucket = settings.GCS_BUCKET
    if args.src == "local" and not bucket:
        raise SystemExit(
            "--bucket must be provided (or GCS_BUCKET env set) when loading local files."
        )

    if args.max_files is not None and args.max_files <= 0:
        raise SystemExit("--max-files must be a positive integer.")

    storage_client = storage.Client() if args.src in ("local", "gcs") else None
    bq_client = bigquery.Client(project=settings.GCP_PROJECT_ID)

    if not args.dry_run:
        ensure_ingestion_log_table(bq_client)

    plan = build_plan(
        bq_client=bq_client,
        storage_client=storage_client,
        bucket=bucket,
        source=args.src,
        since=since_date,
    )
    print_plan(plan, since=since_date, max_files=args.max_files)

    if args.dry_run:
        LOGGER.info("Dry-run complete. No load jobs executed.")
        return 0

    files_to_load = [item for item in plan if item.skip_reason is None and not item.already_loaded]
    if args.max_files is not None:
        files_to_load = files_to_load[: args.max_files]

    loaded_count = 0
    for item in files_to_load:
        load_file(
            bq_client=bq_client,
            storage_client=storage_client,
            bucket=bucket,
            item=item,
        )
        loaded_count += 1

    LOGGER.info("Completed load run: %d file(s) ingested.", loaded_count)
    return 0


def build_plan(
    *,
    bq_client: bigquery.Client,
    storage_client: storage.Client | None,
    bucket: str | None,
    source: str,
    since: date | None,
) -> list[PlanItem]:
    plan: list[PlanItem] = []
    for job in JOBS:
        files = discover_files(job=job, source=source, storage_client=storage_client, bucket=bucket)
        for file_ref in files:
            if since and file_ref.extract_date and file_ref.extract_date < since:
                plan.append(
                    PlanItem(
                        job=job,
                        file=file_ref,
                        hash_md5=None,
                        skip_reason=f"extract_date {file_ref.extract_date} < {since}",
                    )
                )
                continue
            hash_md5 = compute_file_hash(file_ref, storage_client)
            already = already_loaded(
                bq_client=bq_client,
                job=job,
                source_path=file_ref.source_path,
                hash_md5=hash_md5,
            )
            plan.append(
                PlanItem(
                    job=job,
                    file=file_ref,
                    hash_md5=hash_md5,
                    already_loaded=already,
                )
            )
    return plan


def discover_files(
    *,
    job: JobSpec,
    source: str,
    storage_client: storage.Client | None,
    bucket: str | None,
) -> Iterator[FileRef]:
    if source == "local":
        yield from discover_local_files(job)
    elif source == "gcs":
        if not bucket:
            raise RuntimeError("Bucket is required for GCS discovery.")
        if storage_client is None:
            raise RuntimeError("GCS discovery requires a storage client.")
        yield from discover_gcs_files(job, storage_client, bucket)
    else:
        raise ValueError(f"Unsupported source {source}")


def discover_local_files(job: JobSpec) -> Iterator[FileRef]:
    root = RAW_ROOT_LOCAL
    for pattern in job.patterns:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            extract = infer_extract_date(relative)
            size = path.stat().st_size if path.exists() else None
            yield FileRef(
                source_path=str(path),
                relative_path=relative,
                extract_date=extract,
                size=size,
                is_gcs=False,
                local_path=path,
            )


def discover_gcs_files(
    job: JobSpec, storage_client: storage.Client, bucket: str
) -> Iterator[FileRef]:
    for pattern in job.patterns:
        prefix = build_gcs_prefix(pattern)
        full_prefix = f"{RAW_ROOT_GCS}/{prefix}" if prefix else RAW_ROOT_GCS
        for blob in storage_client.list_blobs(bucket, prefix=full_prefix):
            if blob.name.endswith("/"):
                continue
            relative = (
                blob.name[len(f"{RAW_ROOT_GCS}/") :]
                if blob.name.startswith(f"{RAW_ROOT_GCS}/")
                else blob.name
            )
            if not fnmatch.fnmatch(relative, pattern):
                continue
            extract = infer_extract_date(relative)
            size = blob.size
            yield FileRef(
                source_path=f"gs://{bucket}/{blob.name}",
                relative_path=relative,
                extract_date=extract,
                size=size,
                is_gcs=True,
                blob=blob,
            )


def build_gcs_prefix(pattern: str) -> str:
    for idx, char in enumerate(pattern):
        if char in "*?[":
            slash_idx = pattern.rfind("/", 0, idx)
            return pattern[: slash_idx + 1] if slash_idx >= 0 else ""
    slash_idx = pattern.rfind("/")
    return pattern[: slash_idx + 1] if slash_idx >= 0 else pattern


def infer_extract_date(path: str) -> date | None:
    if "extract_date=" in path:
        fragment = path.split("extract_date=", 1)[1]
        date_str = fragment.split("/", 1)[0]
        try:
            return date.fromisoformat(date_str)
        except ValueError:
            return None
    if "snapshot_at=" in path:
        fragment = path.split("snapshot_at=", 1)[1]
        label = fragment.split("/", 1)[0]
        date_part = label.split("T", 1)[0]
        try:
            return date.fromisoformat(date_part)
        except ValueError:
            return None
    return None


def compute_file_hash(file_ref: FileRef, storage_client: storage.Client | None) -> str:
    if not file_ref.is_gcs and file_ref.local_path:
        hashed = hash_from_local_manifest(file_ref.local_path)
        if hashed:
            return hashed
        return md5_file(file_ref.local_path)
    if file_ref.is_gcs and file_ref.blob:
        hashed = hash_from_gcs_manifest(file_ref.blob, storage_client)
        if hashed:
            return hashed
        if file_ref.blob.md5_hash:
            return base64.b64decode(file_ref.blob.md5_hash).hex()
        if storage_client:
            data = file_ref.blob.download_as_bytes()
            return md5_bytes(data)
    raise RuntimeError(f"Unable to compute hash for {file_ref.source_path}")


_MANIFEST_CACHE_LOCAL: dict[Path, dict] = {}
_MANIFEST_CACHE_GCS: dict[str, dict] = {}


def hash_from_local_manifest(path: Path) -> str | None:
    directory = path.parent
    manifest = load_local_manifest(directory)
    if not manifest:
        return None
    files = manifest.get("files") or {}
    entry = files.get(path.name)
    if entry and entry.get("hash_md5"):
        return entry["hash_md5"]
    return None


def load_local_manifest(directory: Path) -> dict | None:
    if directory in _MANIFEST_CACHE_LOCAL:
        return _MANIFEST_CACHE_LOCAL[directory]
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        _MANIFEST_CACHE_LOCAL[directory] = {}
        return {}
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        manifest = {}
    _MANIFEST_CACHE_LOCAL[directory] = manifest
    return manifest


def hash_from_gcs_manifest(blob: storage.Blob, storage_client: storage.Client | None) -> str | None:
    directory = blob.name.rsplit("/", 1)[0]
    manifest_key = f"{blob.bucket.name}/{directory}"
    if manifest_key in _MANIFEST_CACHE_GCS:
        manifest = _MANIFEST_CACHE_GCS[manifest_key]
    else:
        manifest = {}
        if storage_client:
            manifest_blob = blob.bucket.blob(f"{directory}/manifest.json")
            if manifest_blob.exists(storage_client):
                try:
                    manifest = json.loads(manifest_blob.download_as_text())
                except json.JSONDecodeError:
                    manifest = {}
        _MANIFEST_CACHE_GCS[manifest_key] = manifest
    files = manifest.get("files") or {}
    entry = files.get(blob.name.rsplit("/", 1)[-1])
    if entry and entry.get("hash_md5"):
        return entry["hash_md5"]
    return None


def md5_file(path: Path) -> str:
    """
    Compute the MD5 hash of a file using hashlib.md5 with usedforsecurity=False.
    This is intended for data integrity checking only, not for cryptographic security purposes.
    """
    hasher = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def ensure_ingestion_log_table(bq_client: bigquery.Client) -> None:
    dataset = settings.BQ_DATASET_RAW
    project = settings.GCP_PROJECT_ID
    table_id = f"{project}.{dataset}.{INGESTION_LOG_TABLE}"
    try:
        bq_client.get_table(table_id)
        return
    except NotFound:
        pass
    schema = [
        bigquery.SchemaField("_source_path", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("_hash_md5", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("_loaded_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("table", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("rows", "INT64", mode="REQUIRED"),
    ]
    table = bigquery.Table(table_id, schema=schema)
    bq_client.create_table(table)
    LOGGER.info("Created ingestion log table %s", table_id)


def ensure_destination_table(bq_client: bigquery.Client, job: JobSpec) -> None:
    table_id = job.fq_table()
    try:
        bq_client.get_table(table_id)
        return
    except NotFound:
        pass
    table = bigquery.Table(table_id, schema=job.table_schema())
    if job.partition:
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field=job.partition.field,
        )
    if job.clustering:
        table.clustering_fields = list(job.clustering.fields)
    bq_client.create_table(table)
    LOGGER.info("Created table %s", table_id)


def build_load_config(job: JobSpec) -> bigquery.LoadJobConfig:
    csv_opts = job.csv_options
    return bigquery.LoadJobConfig(
        schema=job.source_schema(),
        source_format=bigquery.SourceFormat.CSV,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        skip_leading_rows=csv_opts.skip_leading_rows,
        field_delimiter=csv_opts.field_delimiter,
        quote_character=csv_opts.quote_character,
        allow_quoted_newlines=csv_opts.allow_quoted_newlines,
        encoding=csv_opts.encoding,
        null_marker=csv_opts.null_marker,
    )


def already_loaded(
    *,
    bq_client: bigquery.Client,
    job: JobSpec,
    source_path: str,
    hash_md5: str,
) -> bool:
    table_id = f"{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_RAW}.{INGESTION_LOG_TABLE}"
    query = (
        f"SELECT 1 FROM `{table_id}` "
        "WHERE _source_path = @source_path AND _hash_md5 = @hash_md5 "
        "LIMIT 1"
    )
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("source_path", "STRING", source_path),
            bigquery.ScalarQueryParameter("hash_md5", "STRING", hash_md5),
        ]
    )
    try:
        result = bq_client.query(query, job_config=job_config).result()
    except NotFound:
        return False
    return any(result)


def print_plan(plan: Iterable[PlanItem], *, since: date | None, max_files: int | None) -> None:
    to_load = [item for item in plan if item.skip_reason is None and not item.already_loaded]
    total_new = len(to_load)
    if max_files is not None:
        total_new = min(total_new, max_files)
    LOGGER.info("Load plan (since=%s max_files=%s)", since, max_files)
    for item in plan:
        status = "LOAD"
        if item.skip_reason:
            status = "SKIP"
        elif item.already_loaded:
            status = "DONE"
        hash_part = f"hash={item.hash_md5}" if item.hash_md5 else "hash=?"
        meta = f"extract_date={item.file.extract_date}" if item.file.extract_date else ""
        reason = f" ({item.skip_reason})" if item.skip_reason else ""
        if item.already_loaded:
            reason = " (already loaded)"
        print(
            f"{status:>4} | {item.job.name:<25} -> {item.job.table:<28} {item.file.source_path} "
            f"{hash_part} {meta}{reason}"
        )
    LOGGER.info(
        "Plan summary: %d total items, %d new file(s) to load%s.",
        len(plan),
        total_new,
        f", capped to {max_files}" if max_files is not None else "",
    )


def load_file(
    *,
    bq_client: bigquery.Client,
    storage_client: storage.Client | None,
    bucket: str | None,
    item: PlanItem,
) -> None:
    if item.hash_md5 is None:
        raise RuntimeError("Cannot load file without hash.")
    ensure_destination_table(bq_client, item.job)
    load_config = build_load_config(item.job)
    temp_table_name = f"__tmp_{item.job.name}_{uuid.uuid4().hex[:8]}"
    temp_table_id = f"{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_RAW}.{temp_table_name}"
    temp_table = bigquery.Table(temp_table_id, schema=item.job.source_schema())
    bq_client.create_table(temp_table)
    LOGGER.info("Created temp table %s", temp_table_id)

    remove_temp_blob: storage.Blob | None = None
    source_uri: str
    if item.file.is_gcs:
        source_uri = item.file.source_path
    else:
        if storage_client is None or not bucket:
            raise RuntimeError("Local loads require storage client and bucket.")
        remove_temp_blob, source_uri = upload_local_to_tmp(
            storage_client, bucket, item.file.local_path
        )
    try:
        job = bq_client.load_table_from_uri(source_uri, temp_table_id, job_config=load_config)
        result = job.result()
        output_rows = result.output_rows or 0
        LOGGER.info(
            "Loaded %s rows from %s into temp table %s",
            output_rows,
            item.file.source_path,
            temp_table_id,
        )
        ingested_at = datetime.now(UTC)
        insert_rows_into_destination(
            bq_client=bq_client,
            job=item.job,
            temp_table_id=temp_table_id,
            dest_table_id=item.job.fq_table(),
            ingested_at=ingested_at,
            source_path=item.file.source_path,
            extract_date=item.file.extract_date or ingested_at.date(),
            hash_md5=item.hash_md5,
        )
        record_loaded(
            bq_client=bq_client,
            job=item.job,
            source_path=item.file.source_path,
            hash_md5=item.hash_md5,
            rows=output_rows,
            loaded_at=ingested_at,
        )
    finally:
        bq_client.delete_table(temp_table_id, not_found_ok=True)
        LOGGER.info("Dropped temp table %s", temp_table_id)
        if remove_temp_blob:
            remove_temp_blob.delete()
            LOGGER.info(
                "Deleted temp object gs://%s/%s",
                remove_temp_blob.bucket.name,
                remove_temp_blob.name,
            )


def upload_local_to_tmp(
    storage_client: storage.Client,
    bucket_name: str,
    path: Path | None,
) -> tuple[storage.Blob, str]:
    if path is None:
        raise RuntimeError("Local path is required to upload.")
    bucket = storage_client.bucket(bucket_name)
    blob_name = f"tmp/{uuid.uuid4().hex}/{path.name}"
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(path))
    return blob, f"gs://{bucket_name}/{blob_name}"


def insert_rows_into_destination(
    *,
    bq_client: bigquery.Client,
    job: JobSpec,
    temp_table_id: str,
    dest_table_id: str,
    ingested_at: datetime,
    source_path: str,
    extract_date: date,
    hash_md5: str,
) -> None:
    all_columns = [col.name for col in job.columns] + [meta.name for meta in META_COLUMNS]
    column_list = ", ".join(f"`{name}`" for name in all_columns)
    select_columns = ", ".join(f"`{col.name}`" for col in job.columns)
    query = (
        f"INSERT INTO `{dest_table_id}` ({column_list}) "
        f"SELECT {select_columns}, @ingested_at, @source_path, @extract_date, @hash_md5 "
        f"FROM `{temp_table_id}`"
    )
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("ingested_at", "TIMESTAMP", ingested_at),
            bigquery.ScalarQueryParameter("source_path", "STRING", source_path),
            bigquery.ScalarQueryParameter("extract_date", "DATE", extract_date),
            bigquery.ScalarQueryParameter("hash_md5", "STRING", hash_md5),
        ]
    )
    bq_client.query(query, job_config=job_config).result()
    LOGGER.info("Inserted rows into %s with source_path=%s", dest_table_id, source_path)


def record_loaded(
    *,
    bq_client: bigquery.Client,
    job: JobSpec,
    source_path: str,
    hash_md5: str,
    rows: int,
    loaded_at: datetime,
) -> None:
    table_id = f"{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_RAW}.{INGESTION_LOG_TABLE}"
    payload = [
        {
            "_source_path": source_path,
            "_hash_md5": hash_md5,
            "_loaded_at": loaded_at.isoformat(),
            "table": job.table,
            "rows": rows,
        }
    ]
    errors = bq_client.insert_rows_json(table_id, payload)
    if errors:
        raise RuntimeError(f"Failed to append ingestion log for {source_path}: {errors}")
    LOGGER.info("Recorded ingestion log entry for %s", source_path)


if __name__ == "__main__":
    sys.exit(main())
