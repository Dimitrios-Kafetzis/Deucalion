# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis

"""Deucalion: back up an Ubuntu machine to an external drive and rebuild it later."""

__version__ = "0.2.1"

import logging as _logging

_logging.getLogger("deucalion").addHandler(_logging.NullHandler())
