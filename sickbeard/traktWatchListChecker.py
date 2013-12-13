# Author: Frank Fenton
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
import time
import os

import sickbeard

from sickbeard import db

from sickbeard import encodingKludge as ek
from sickbeard import logger
from sickbeard import helpers
from sickbeard import search_queue
from sickbeard.common import SNATCHED, SNATCHED_PROPER, DOWNLOADED, SKIPPED, UNAIRED, IGNORED, ARCHIVED, WANTED, UNKNOWN
from lib.trakt import *

class TraktChecker():
    def __init__(self):
        self.todoWanted = []
        self.todoBacklog = []

    def run(self):
        if sickbeard.TRAKT_USE_WATCHLIST:
            self.todoWanted = []  #its about to all get re-added
            if len(sickbeard.ROOT_DIRS.split('|')) < 2:
                logger.log(u"No default root directory", logger.ERROR)
                return
            self.updateShows()
            self.updateEpisodes()
            self.updateWantedList()

    def updateWantedList(self):

	num_of_download = sickbeard.TRAKT_NUM_EP

        logger.log(u"Starting trakt show wanted list check", logger.DEBUG)

	myDB = db.DBConnection()

	sql_selection="SELECT show_name, tvdb_id, season, episode, paused FROM (SELECT * FROM tv_shows s,tv_episodes e WHERE s.tvdb_id = e.showid) T1 WHERE T1.paused = 0 and T1.episode_id IN (SELECT T2.episode_id FROM tv_episodes T2 WHERE T2.showid = T1.tvdb_id and T2.status in (2,3,5) and T2.season!=0 ORDER BY T2.season,T2.episode LIMIT 1) ORDER BY T1.show_name,season,episode"
	results = myDB.select(sql_selection)

	for cur_result in results:

		num_op_ep=''

		last_per_season = TraktCall("show/seasons.json/%API%/" + str(cur_result["tvdb_id"]), sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD)
		watched = TraktCall("user/library/shows/watched.json/%API%/" + sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD)
        	if last_per_season is None or watched is None:
            		logger.log(u"Could not connect to trakt service, aborting watchlist update", logger.ERROR)
            		return

		tvdb_id = str(cur_result["tvdb_id"])
		show_name = (cur_result["show_name"])
		sn_sb = cur_result["season"]
		ep_sb = cur_result["episode"]

		last_episode = ''

		logger.log(u"TVDB_ID: " + str(tvdb_id) + ", Show: " + show_name + ", Season: " + str(sn_sb) + ", Episode: " + str(ep_sb), logger.DEBUG)

		if tvdb_id not in (show["tvdb_id"] for show in watched):
			logger.log(u"Show not founded in Watched list", logger.DEBUG)
			if sn_sb >= 1 and ep_sb > num_of_download:
				logger.log(u"First five episode already downloaded", logger.DEBUG)
				continue
			else:
				sn_sb = 1
				ep_sb = 1
				num_of_ep = num_of_download - ep_sb
				episode = 0
		else:
			logger.log(u"Show founded in Watched list", logger.DEBUG)

			show_watched = [show for show in watched if show["tvdb_id"] == tvdb_id]
			
			season = show_watched[0]['seasons'][0]['season']
			episode = show_watched[0]['seasons'][0]['episodes'][-1]
			logger.log(u"Last watched, Season: " + str(season) + " - Episode: " + str(episode), logger.DEBUG)

			if (sn_sb < season):
				logger.log(u"TV Show already watched", logger.DEBUG)
				continue

			last_season = [last_x_season_wc for last_x_season_wc in last_per_season if last_x_season_wc['season'] == season]
			last_episode = last_season[0]['episodes']
			logger.log(u"Last episode for the season " + str(last_season[0]['season']) + " is " + str(last_episode), logger.DEBUG)

			if (episode == last_episode):
				num_of_ep = num_of_download - ep_sb
			else:
				num_of_ep = num_of_download - (ep_sb - episode)
				if sn_sb > season:
					num_of_ep = num_of_ep - last_episode

		logger.log(u"Number of Episode to Download: " + str(num_of_ep), logger.DEBUG)
		newShow = helpers.findCertainShow(sickbeard.showList, int(tvdb_id))
		for x in range(0,num_of_ep+1):
			logger.log(u"Episode to be wanted: " +  str(ep_sb) + "+" + str(x), logger.DEBUG)
			if ep_sb+x <= last_episode or last_episode == None:
				if ep_sb+x > episode:
       	        			self.setEpisodeToWanted(newShow, sn_sb, ep_sb+x)
				else:
       	        			self.setEpisodeToArchived(newShow, sn_sb, ep_sb+x)
			else:
              			self.setEpisodeToWanted(newShow, sn_sb+1, ep_sb+x-last_episode)
                   	self.startBacklog(newShow)

    def updateShows(self):
        logger.log(u"Starting trakt show watchlist check", logger.DEBUG)
        watchlist = TraktCall("user/watchlist/shows.json/%API%/" + sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD)
        if watchlist is None:
            logger.log(u"Could not connect to trakt service, aborting watchlist update", logger.ERROR)
            return
        for show in watchlist:
            if int(sickbeard.TRAKT_METHOD_ADD) != 2:
                self.addDefaultShow(show["tvdb_id"], show["title"], SKIPPED)
            else:
                self.addDefaultShow(show["tvdb_id"], show["title"], WANTED)

            if int(sickbeard.TRAKT_METHOD_ADD) == 1:
                newShow = helpers.findCertainShow(sickbeard.showList, int(show["tvdb_id"]))
                if newShow is not None:
                    self.setEpisodeToWanted(newShow, 1, 1)
                    self.startBacklog(newShow)
                else:
                    self.todoWanted.append((int(show["tvdb_id"]), 1, 1))
            self.todoWanted.append((int(show["tvdb_id"]), -1, -1)) #used to pause new shows if the settings say to

    def updateEpisodes(self):
        """
        Sets episodes to wanted that are in trakt watchlist
        """
        logger.log(u"Starting trakt episode watchlist check", logger.DEBUG)
        watchlist = TraktCall("user/watchlist/episodes.json/%API%/" + sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD)
        if watchlist is None:
            logger.log(u"Could not connect to trakt service, aborting watchlist update", logger.ERROR)
            return
        for show in watchlist:
            self.addDefaultShow(show["tvdb_id"], show["title"], SKIPPED)
            newShow = helpers.findCertainShow(sickbeard.showList, int(show["tvdb_id"]))
            for episode in show["episodes"]:
                if newShow is not None:
                    self.setEpisodeToWanted(newShow, episode["season"], episode["number"])
                else:
                    self.todoWanted.append((int(show["tvdb_id"]), episode["season"], episode["number"]))
            self.startBacklog(newShow)

    def addDefaultShow(self, tvdbid, name, status):
        """
        Adds a new show with the default settings
        """
        showObj = helpers.findCertainShow(sickbeard.showList, int(tvdbid))
        if showObj != None:
            return
        logger.log(u"Adding show " + tvdbid)
        root_dirs = sickbeard.ROOT_DIRS.split('|')
        location = root_dirs[int(root_dirs[0]) + 1]

        showPath = ek.ek(os.path.join, location, helpers.sanitizeFileName(name))
        dir_exists = helpers.makeDir(showPath)
        if not dir_exists:
            logger.log(u"Unable to create the folder " + showPath + ", can't add the show", logger.ERROR)
            return
        else:
            helpers.chmodAsParent(showPath)
        sickbeard.showQueueScheduler.action.addShow(int(tvdbid), showPath, status, int(sickbeard.QUALITY_DEFAULT), int(sickbeard.FLATTEN_FOLDERS_DEFAULT))

    def setEpisodeToArchived(self, show, s, e):
        """
        Sets an episode to wanted, only is it is currently skipped
        """
        epObj = show.getEpisode(int(s), int(e))
        if epObj == None:
            return
        with epObj.lock:
            if epObj.status != SKIPPED:
                return
            logger.log(u"Setting episode s"+str(s)+"e"+str(e)+" of show " + show.name + " to wanted")
#            # figure out what segment the episode is in and remember it so we can backlog it
#            if epObj.show.air_by_date:
#                ep_segment = str(epObj.airdate)[:7]
#            else:
#                ep_segment = epObj.season

            epObj.status = ARCHIVED
            epObj.saveToDB()
#            backlog = (show, ep_segment)
#            if self.todoBacklog.count(backlog)==0:
#                self.todoBacklog.append(backlog)


    def setEpisodeToWanted(self, show, s, e):
        """
        Sets an episode to wanted, only is it is currently skipped
        """
        epObj = show.getEpisode(int(s), int(e))
        if epObj == None:
            return
        with epObj.lock:
            if epObj.status != SKIPPED:
                return
            logger.log(u"Setting episode s"+str(s)+"e"+str(e)+" of show " + show.name + " to wanted")
            # figure out what segment the episode is in and remember it so we can backlog it
            if epObj.show.air_by_date:
                ep_segment = str(epObj.airdate)[:7]
            else:
                ep_segment = epObj.season

            epObj.status = WANTED
            epObj.saveToDB()
            backlog = (show, ep_segment)
            if self.todoBacklog.count(backlog)==0:
                self.todoBacklog.append(backlog)


    def manageNewShow(self, show):
        episodes = [i for i in self.todoWanted if i[0] == show.tvdbid]
        for episode in episodes:
            self.todoWanted.remove(episode)
            if episode[1] == -1 and sickbeard.TRAKT_START_PAUSED:
                show.paused = 1
                continue
            self.setEpisodeToWanted(show, episode[1], episode[2])
        self.startBacklog(show)

    def startBacklog(self, show):
        segments = [i for i in self.todoBacklog if i[0] == show]
        for segment in segments:
            cur_backlog_queue_item = search_queue.BacklogQueueItem(show, segment[1])
            sickbeard.searchQueueScheduler.action.add_item(cur_backlog_queue_item)
            logger.log(u"Starting backlog for " + show.name + " season " + str(segment[1]) + " because some eps were set to wanted")
            self.todoBacklog.remove(segment)


