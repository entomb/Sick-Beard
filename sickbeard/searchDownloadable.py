# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement

import datetime
import threading

import sickbeard

from sickbeard import db, scheduler
from sickbeard import search_queue
from sickbeard import logger
from sickbeard import ui
#from sickbeard.common import *

class DownloadableSearchScheduler(scheduler.Scheduler):

    def forceSearch(self):
        self.action._set_last_DownloadableSearch(1)
        self.lastRun = datetime.datetime.fromordinal(1)

    def nextRun(self):
        if self.action._last_DownloadableSearch <= 1:
            return datetime.date.today()
        else:
            return datetime.date.fromordinal(self.action._last_DownloadableSearch + self.action.cycleTime)

class DownloadableSearcher:

    def __init__(self):

        self._last_DownloadableSearch = self._get_last_DownloadableSearch()
        self.cycleTime = 7
        self.lock = threading.Lock()
        self.amActive = False
        self.amPaused = False
        self.amWaiting = False

        self._resetPI()

    def _resetPI(self):
        self.percentDone = 0
        self.currentSearchInfo = {'title': 'Initializing'}

    def getProgressIndicator(self):
        if self.amActive:
            return ui.ProgressIndicator(self.percentDone, self.currentSearchInfo)
        else:
            return None

    def am_running(self):
        logger.log(u"amWaiting: "+str(self.amWaiting)+", amActive: "+str(self.amActive), logger.DEBUG)
        return (not self.amWaiting) and self.amActive

    def searchDownloadable(self, which_shows=None):

        if which_shows:
            show_list = which_shows
        else:
            show_list = sickbeard.showList

        if self.amActive == True:
            logger.log(u"Downloadable search is still running, not starting it again", logger.DEBUG)
            return

        self._get_last_DownloadableSearch()

        curDate = datetime.date.today().toordinal()
        fromDate = datetime.date.fromordinal(1)

        if not which_shows and not curDate - self._last_DownloadableSearch >= self.cycleTime:
            logger.log(u"Running limited Downloadable search on recently missed episodes only")
            fromDate = datetime.date.today() - datetime.timedelta(days=7)

        self.amActive = True
        self.amPaused = False

        #myDB = db.DBConnection()
        #numSeasonResults = myDB.select("SELECT DISTINCT(season), showid FROM tv_episodes ep, tv_shows show WHERE season != 0 AND ep.showid = show.tvdb_id AND ep.airdate > ?", [fromDate.toordinal()])

        # get separate lists of the season/date shows
        #season_shows = [x for x in show_list if not x.air_by_date]
        air_by_date_shows = [x for x in show_list if x.air_by_date]

        # figure out how many segments of air by date shows we're going to do
        air_by_date_segments = []
        for cur_id in [x.tvdbid for x in air_by_date_shows]:
            air_by_date_segments += self._get_air_by_date_segments(cur_id, fromDate) 

        logger.log(u"Air-by-date segments: "+str(air_by_date_segments), logger.DEBUG)

        #totalSeasons = float(len(numSeasonResults) + len(air_by_date_segments))
        #numSeasonsDone = 0.0

        # go through non air-by-date shows and see if they need any episodes
        for curShow in show_list:

            if curShow.air_by_date:
                segments = [x[1] for x in self._get_air_by_date_segments(curShow.tvdbid, fromDate)]
            else:
                segments = self._get_season_segments(curShow.tvdbid, fromDate)

            for cur_segment in segments:

                self.currentSearchInfo = {'title': curShow.name + " Season "+str(cur_segment)}

                download_search_queue_item = search_queue.DownloadSearchQueueItem(curShow, cur_segment)

                if not download_search_queue_item.availableSeason:
                    logger.log(u"Nothing in season "+str(cur_segment)+" needs to be check if available, skipping this season", logger.DEBUG)
                else:
                   sickbeard.searchQueueScheduler.action.add_item(download_search_queue_item)  #@UndefinedVariable 

        # don't consider this an actual downloadable search if we only did recent eps
        # or if we only did certain shows
        if fromDate == datetime.date.fromordinal(1) and not which_shows:
            self._set_last_DownloadableSearch(curDate)

        self.amActive = False
        self._resetPI()

    def _get_last_DownloadableSearch(self):

        logger.log(u"Retrieving the last check time from the DB", logger.DEBUG)

        myDB = db.DBConnection()
        sqlResults = myDB.select("SELECT * FROM info")

        if len(sqlResults) == 0:
            last_DownloadableSearch = 1
        elif sqlResults[0]["last_DownloadableSearch"] == None or sqlResults[0]["last_DownloadableSearch"] == "":
            last_DownloadableSearch = 1
        else:
            last_DownloadableSearch = int(sqlResults[0]["last_DownloadableSearch"])

        self._last_DownloadableSearch = last_DownloadableSearch
        return self._last_DownloadableSearch

    def _get_season_segments(self, tvdb_id, fromDate):
        myDB = db.DBConnection()
        sqlResults = myDB.select("SELECT DISTINCT(season) as season FROM tv_episodes WHERE showid = ? AND season > 0 and airdate > ?", [tvdb_id, fromDate.toordinal()])
        return [int(x["season"]) for x in sqlResults]

    def _get_air_by_date_segments(self, tvdb_id, fromDate):
        # query the DB for all dates for this show
        myDB = db.DBConnection()
        num_air_by_date_results = myDB.select("SELECT airdate, showid FROM tv_episodes ep, tv_shows show WHERE season != 0 AND ep.showid = show.tvdb_id AND show.paused = 0 ANd ep.airdate > ? AND ep.showid = ?",
                                 [fromDate.toordinal(), tvdb_id])

        # break them apart into month/year strings
        air_by_date_segments = []
        for cur_result in num_air_by_date_results:
            cur_date = datetime.date.fromordinal(int(cur_result["airdate"]))
            cur_date_str = str(cur_date)[:7]
            cur_tvdb_id = int(cur_result["showid"])
            
            cur_result_tuple = (cur_tvdb_id, cur_date_str)
            if cur_result_tuple not in air_by_date_segments:
                air_by_date_segments.append(cur_result_tuple)
        
        return air_by_date_segments

    def _set_last_DownloadableSearch(self, when):

        logger.log(u"Setting the last downloadable search in the DB to " + str(when), logger.DEBUG)

        myDB = db.DBConnection()
        sqlResults = myDB.select("SELECT * FROM info")

        if len(sqlResults) == 0:
            myDB.action("INSERT INTO info (last_downloadablesearch, last_backlog, last_TVDB) VALUES (?,?,?)", [str(when), 0, 0])
        else:
            myDB.action("UPDATE info SET last_downloadablesearch=" + str(when))


    def run(self):
        try:
            self.searchDownloadable()
        except:
            self.amActive = False
            raise
