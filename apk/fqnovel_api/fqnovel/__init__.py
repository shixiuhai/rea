"""fqnovel_api -- client for the reverse-engineered fqnovel (com.dragon.read) API."""

from .client import (
    FqnovelClient,
    GatedError,
    Response,
    extract_book_ids,
    extract_contents,
    extract_item_ids,
)
from .common_params import DeviceProfile, build_common_params
from .signer import (
    HeaderFileSigner,
    NativeSigner,
    NullSigner,
    RemoteSigner,
    Signer,
    default_signer,
)

__all__ = [
    "FqnovelClient",
    "Response",
    "GatedError",
    "extract_book_ids",
    "extract_item_ids",
    "extract_contents",
    "DeviceProfile",
    "build_common_params",
    "Signer",
    "NullSigner",
    "HeaderFileSigner",
    "RemoteSigner",
    "NativeSigner",
    "default_signer",
]

__version__ = "1.0.0"
