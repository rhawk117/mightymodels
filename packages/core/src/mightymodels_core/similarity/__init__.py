"""The similarity records, their repository seams, the service and the sqlite stores behind them."""

from .matching import CANDIDATE_CAP, MATCH_OVERLAP, content_words, overlap
from .records import Duplicate, Match, ScoutReport, Written
from .repository import ScoutReportRepository, SimilarityRepository
from .services import IncomingReport, SimilarityOptions, SimilarityService, StoredReport
from .sqlite_scout_reports import SqliteScoutReportRepository
from .sqlite_similarity import SqliteSimilarityRepository

__all__ = [
    'CANDIDATE_CAP',
    'MATCH_OVERLAP',
    'Duplicate',
    'IncomingReport',
    'Match',
    'ScoutReport',
    'ScoutReportRepository',
    'SimilarityOptions',
    'SimilarityRepository',
    'SimilarityService',
    'SqliteScoutReportRepository',
    'SqliteSimilarityRepository',
    'StoredReport',
    'Written',
    'content_words',
    'overlap',
]
