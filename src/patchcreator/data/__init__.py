"""External dataset catalogue and explicit cache management."""

from .catalog import (
    ChecksumMismatchError,
    DataCatalog,
    DataSource,
    DataSourceError,
    DatasetNotInstalledError,
    fetch_dataset,
    fetch_source,
    is_dataset_installed,
    load_data_catalog,
    require_dataset,
    resolve_data_root,
)

__all__ = [
    "ChecksumMismatchError",
    "DataCatalog",
    "DataSource",
    "DataSourceError",
    "DatasetNotInstalledError",
    "fetch_dataset",
    "fetch_source",
    "is_dataset_installed",
    "load_data_catalog",
    "require_dataset",
    "resolve_data_root",
]
