"""TiMi_HOK_Game_Translator.vcs 子包。

对外 API::

    from TiMi_HOK_Game_Translator.vcs import (
        VcsClient, VcsCredentials, VcsStatus,
        SvnClient, GitClient, PerforceClient, MockClient,
        create_vcs_client, register_vcs_client,
    )
"""

from .base import VcsClient, VcsCommandResult, VcsCredentials, VcsStatus
from .factory import create_vcs_client, register_vcs_client
from .git_client import GitClient
from .mock_client import MockClient
from .perforce_client import PerforceClient
from .svn_client import SvnClient

__all__ = [
    "GitClient",
    "MockClient",
    "PerforceClient",
    "SvnClient",
    "VcsClient",
    "VcsCommandResult",
    "VcsCredentials",
    "VcsStatus",
    "create_vcs_client",
    "register_vcs_client",
]
