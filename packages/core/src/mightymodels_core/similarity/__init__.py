"""The similarity records, their repository seams and the sqlite stores behind them."""

from .matching import CANDIDATE_CAP, MATCH_OVERLAP, content_words, overlap
from .records import Duplicate, Match, ScoutReport, Written
from .repository import ScoutReportRepository, SimilarityRepository
from .sqlite_scout_reports import SqliteScoutReportRepository
from .sqlite_similarity import SqliteSimilarityRepository

__all__ = [
    'CANDIDATE_CAP',
    'MATCH_OVERLAP',
    'Duplicate',
    'Match',
    'ScoutReport',
    'ScoutReportRepository',
    'SimilarityRepository',
    'SqliteScoutReportRepository',
    'SqliteSimilarityRepository',
    'Written',
    'content_words',
    'overlap',
]
