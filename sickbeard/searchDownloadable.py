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

        self.amActive = True
        self.amPaused = False


        for show in show_list:

                self.currentSearchInfo = {'title': show.name}

                download_search_queue_item = search_queue.DownloadSearchQueueItem(show)

                sickbeard.searchQueueScheduler.action.add_item(download_search_queue_item)  #@UndefinedVariable

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
