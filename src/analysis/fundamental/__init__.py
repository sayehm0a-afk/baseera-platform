"""Fundamental analysis: financial-statement-derived ratios.

Pure computation only -- no I/O, no database, no awareness of
src/analysis/indicators/ or any other engine. See src/analysis/core/
for the shared output contract this package's results satisfy, and
src/analysis/fundamental/fundamental_loader.py for the only module in
this package that touches a database session.
"""
