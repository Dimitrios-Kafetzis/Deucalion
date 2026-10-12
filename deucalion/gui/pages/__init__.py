# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis

"""The app's pages, one module each."""

from .backup import BackupPage
from .drives import DrivesPage
from .overview import OverviewPage
from .rebuild import RebuildPage
from .removed import RemovedPage
from .restore import RestorePage
from .settings import SettingsPage

__all__ = ["BackupPage", "DrivesPage", "OverviewPage", "RebuildPage", "RemovedPage", "RestorePage", "SettingsPage"]
