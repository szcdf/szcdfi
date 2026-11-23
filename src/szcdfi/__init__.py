"""szcdfi -- the cross-platform installer engine for the szcdf dotfiles framework.

One stdlib-only engine that reads a ``.szcdfis`` manifest and applies its
directives (COPY, COPYALL, PREPENDTEXT, APPENDTEXT) with correct, uniform text
handling: UTF-8 without BOM, destination-EOL preservation, and the exact SZCDF
section-marker format. See ADR-0003.
"""

__version__ = "0.1.1"

__all__ = ["__version__"]
