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
from sickbeard.common import SNATCHED, SNATCHED_PROPER, DOWNLOADED, DOWNLOADABLE, SKIPPED, UNAIRED, IGNORED, ARCHIVED, WANTED, UNKNOWN, FAILED
from common import Quality, qualityPresetStrings, statusStrings
from lib.trakt import *

class TraktChecker():
    def __init__(self):
        self.todoWanted = []
        self.todoBacklog = []
	self.ShowWatchlist = []
	self.EpisodeWatchlist = []
        self.ShowProgress = []
        self.EpisodeWatched = []

    def run(self):
        if sickbeard.USE_TRAKT:
            self.todoWanted = []  #its about to all get re-added
            if len(sickbeard.ROOT_DIRS.split('|')) < 2:
                logger.log(u"No default root directory", logger.ERROR)
                return

	    if not self._getShowWatchlist():
                return
	    if not self._getEpisodeWatchlist():
                return
	    if not self._getShowProgress():
                return
	    if not self._getEpisodeWatched():
                return

            self.removeShowFromWatchList()
            self.updateShows()
 	    self.removeEpisodeFromWatchList()
            self.updateEpisodes()
            self.updateWantedList()
            self.addEpisodeToWatchList()
            self.addShowToWatchList()


    def _getEpisodeWatchlist(self):
        
        self.EpisodeWatchlist = TraktCall("user/watchlist/episodes.json/%API%/" + sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD)
        if self.EpisodeWatchlist is None:
            logger.log(u"Could not connect to trakt service, cannot download Episode Watchlist", logger.ERROR)
            return False

        return True

    def _getShowWatchlist(self):

        self.ShowWatchlist = TraktCall("user/watchlist/shows.json/%API%/" + sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD)
        if self.ShowWatchlist is None:
            logger.log(u"Could not connect to trakt service, cannot download Show Watchlist", logger.ERROR)
            return False

        return True

    def _getShowProgress(self):

        self.ShowProgress = TraktCall("user/progress/watched.json/%API%/" + sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD)
        if self.ShowProgress is None:
            logger.log(u"Could not connect to trakt service, cannot download show progress", logger.ERROR)
            return False

        return True

    def _getEpisodeWatched(self):

        self.EpisodeWatched = TraktCall("user/library/shows/watched.json/%API%/" + sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD)
        if self.EpisodeWatched is None:
            logger.log(u"Could not connect to trakt service, cannot download show from library", logger.ERROR)
            return False

        return True

    def refreshEpisodeWatchlist(self):

       if not self._getEpisodeWatchlist():
           return False

    def refreshShowWatchlist(self):

       if not self._getShowWatchlist():
           return False

    def removeEpisodeFromWatchList(self):

	if sickbeard.TRAKT_REMOVE_WATCHLIST and sickbeard.USE_TRAKT:
		logger.log(u"Start looking if some episode has to be removed from watchlist", logger.DEBUG)

		for show in self.EpisodeWatchlist:
			for episode in show["episodes"]:
				newShow = helpers.findCertainShow(sickbeard.showList, int(show["tvdb_id"]))
				if newShow is None:
					logger.log(u"Show: tvdb_id " + show["tvdb_id"] + ", Title " + show["title"] + " not in Sickberad ShowList", logger.DEBUG)
					continue

				ep_obj = newShow.getEpisode(int(episode["season"]), int(episode["number"]))
				if ep_obj is None:
					logger.log(u"Episode: tvdb_id " + show["tvdb_id"] + ", Title " + show["title"] + ", Season " + str(episode["season"]) + ", Episode" + str(episode["number"]) + " not in Sickberad ShowList", logger.DEBUG)
					continue
					
				if ep_obj.status != WANTED and ep_obj.status != UNKNOWN and ep_obj.status not in Quality.SNATCHED and ep_obj.status not in Quality.SNATCHED_PROPER:
					if self.episode_in_watchlist(show["tvdb_id"], episode["season"], episode["number"]):
					        logger.log(u"Removing episode: tvdb_id " + show["tvdb_id"] + ", Title " + show["title"] + ", Season " + str(episode["season"]) + ", Episode " + str(episode["number"]) + ", Status " + str(ep_obj.status) + " from Watchlist", logger.DEBUG)
						if not self.update_watchlist("episode", "remove", show["tvdb_id"], episode["season"], episode["number"]):
                                                    return False

		logger.log(u"Stop looking if some episode has to be removed from watchlist", logger.DEBUG)


    def removeShowFromWatchList(self):

	if sickbeard.TRAKT_REMOVE_SHOW_WATCHLIST and sickbeard.USE_TRAKT:
		logger.log(u"Start looking if some show has to be removed from watchlist", logger.DEBUG)
		for show in self.ShowWatchlist:
			newShow = helpers.findCertainShow(sickbeard.showList, int(show["tvdb_id"]))
			if (newShow is not None) and (newShow.status == "Ended"):
				if self.show_full_wathced(newShow):
					logger.log(u"Deleting show: tvdb_id " + show["tvdb_id"] + ", Title " + show["title"] + " from SickBeard", logger.DEBUG)
                                        newShow.deleteShow()
					logger.log(u"Removing show: tvdb_id " + show["tvdb_id"] + ", Title " + show["title"] + " from Watchlist", logger.DEBUG)
					if not self.update_watchlist("show", "remove", show["tvdb_id"], 0, 0):
                                            return False

		logger.log(u"Stop looking if some show has to be removed from watchlist", logger.DEBUG)
				
    def addEpisodeToWatchList(self, tvdb_id=None):

	if sickbeard.TRAKT_REMOVE_WATCHLIST and sickbeard.USE_TRAKT:
		logger.log(u"Start looking if some WANTED episode need to be added to watchlist", logger.DEBUG)

		myDB = db.DBConnection()
		sql_selection='select showid, show_name, season, episode from tv_episodes,tv_shows where tv_shows.tvdb_id = tv_episodes.showid and tv_episodes.status in ('+','.join([str(x) for x in Quality.SNATCHED + Quality.SNATCHED_PROPER + [WANTED]])+')'
		if tvdb_id is None:
                    episode = myDB.select(sql_selection)
                else:
                    sql_selection=sql_selection+" and showid=?"
                    episode = myDB.select(sql_selection, [tvdb_id])

		if episode is not None:
			for cur_episode in episode:
				if not self.episode_in_watchlist(cur_episode["showid"], cur_episode["season"], cur_episode["episode"]):
					logger.log(u"Episode: tvdb_id " + str(cur_episode["showid"])+ ", Title " +  str(cur_episode["show_name"]) + " " + str(cur_episode["season"]) + "x" + str(cur_episode["episode"]) + " should be added to watchlist", logger.DEBUG)
					if not self.update_watchlist("episode", "add", cur_episode["showid"], cur_episode["season"], cur_episode["episode"]):
                                            return False

		logger.log(u"Stop looking if some WANTED episode need to be added to watchlist", logger.DEBUG)
			
    def addShowToWatchList(self):

	if sickbeard.TRAKT_REMOVE_SHOW_WATCHLIST and sickbeard.USE_TRAKT:
		logger.log(u"Start looking if some show need to be added to watchliast", logger.DEBUG)

		if sickbeard.showList is not None:
			for show in sickbeard.showList:
				if not self.show_in_watchlist(show.tvdbid):
					logger.log(u"Show: tvdb_id " + str(show.tvdbid) + ", Title " +  str(show.name) + " should be added to watchlist", logger.DEBUG)
					if not self.update_watchlist("show", "add", show.tvdbid, 0, 0):
                                            return False
				
		logger.log(u"Stop looking if some show need to be added to watchliast", logger.DEBUG)

    def updateWantedList(self):

	num_of_download = sickbeard.TRAKT_NUM_EP

	if num_of_download == 0:
	   return False

        logger.log(u"Start looking if having " + str(num_of_download) + " episode not watched", logger.DEBUG)

	myDB = db.DBConnection()

	sql_selection="SELECT show_name, tvdb_id, season, episode, paused FROM (SELECT * FROM tv_shows s,tv_episodes e WHERE s.tvdb_id = e.showid) T1 WHERE T1.paused = 0 and T1.episode_id IN (SELECT T2.episode_id FROM tv_episodes T2 WHERE T2.showid = T1.tvdb_id and T2.status in (?,?,?) and T2.season!=0 and airdate is not null ORDER BY T2.season,T2.episode LIMIT 1) ORDER BY T1.show_name,season,episode"
	results = myDB.select(sql_selection,[SKIPPED,DOWNLOADABLE,FAILED])

	for cur_result in results:

		num_op_ep=0
		season = 0
		episode = 0

		last_per_season = TraktCall("show/seasons.json/%API%/" + str(cur_result["tvdb_id"]), sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD)
            	if not last_per_season:
            	    logger.log(u"Could not connect to trakt service, cannot download last season for show", logger.ERROR)
            	    return False

		tvdb_id = str(cur_result["tvdb_id"])
		show_name = (cur_result["show_name"])
		sn_sb = cur_result["season"]
		ep_sb = cur_result["episode"]

		logger.log(u"TVDB_ID: " + str(tvdb_id) + ", Show: " + show_name + " - First skipped Episode: Season " + str(sn_sb) + ", Episode " + str(ep_sb), logger.DEBUG)

		if tvdb_id not in (show["tvdb_id"] for show in self.EpisodeWatched):
			logger.log(u"Show not founded in Watched list", logger.DEBUG)
			if (sn_sb*100+ep_sb) > 100+num_of_download:
				logger.log(u"First " + str(num_of_download) + " episode already downloaded", logger.DEBUG)
				continue
			else:
				sn_sb = 1
				ep_sb = 1
				num_of_ep = num_of_download
				episode = 0
		else:
			logger.log(u"Show founded in Watched list", logger.DEBUG)

			show_watched = [show for show in self.EpisodeWatched if show["tvdb_id"] == tvdb_id]
			
			season = show_watched[0]['seasons'][0]['season']
			episode = show_watched[0]['seasons'][0]['episodes'][-1]
			logger.log(u"Last watched, Season: " + str(season) + " - Episode: " + str(episode), logger.DEBUG)

			num_of_ep = num_of_download - (self._num_ep_for_season(last_per_season, sn_sb, ep_sb) - self._num_ep_for_season(last_per_season, season, episode)) + 1

		logger.log(u"Number of Episode to Download: " + str(num_of_ep), logger.DEBUG)
		newShow = helpers.findCertainShow(sickbeard.showList, int(tvdb_id))

		s = sn_sb
		e = ep_sb

		wanted = False

		for x in range(0,num_of_ep):

			last_s = [last_x_s for last_x_s in last_per_season if last_x_s['season'] == s]
			if episode == 0 or (s*100+e) <= (int(last_s[0]['season'])*100+int(last_s[0]['episodes'])): 

				if (s*100+e) > (season*100+episode):
					logger.log(u"Changed episode to wanted: S" + str(s) + "E"+  str(e), logger.DEBUG)
					if newShow is not None:
       	        				self.setEpisodeToWanted(newShow, s, e)
						if not self.episode_in_watchlist(newShow.tvdbid, s, e):
							if not self.update_watchlist("episode", "add", newShow.tvdbid, s, e):
                                                            return False
						wanted = True
					else:
                    				self.todoWanted.append(int(tvdb_id), s, e)
				else:
					logger.log(u"Changed episode to archived: S" + str(s) + "E"+  str(e), logger.DEBUG)
       	        			self.setEpisodeToArchived(newShow, s, e)
					if self.episode_in_watchlist(newShow.tvdbid, s, e):
						if not self.update_watchlist("episode", "remove", newShow.tvdbid, s, e):
                                                    return False

			if (s*100+e) == (int(last_s[0]['season'])*100+int(last_s[0]['episodes'])):
				s = s + 1
				e = 1
			else:
				e = e + 1
				
		if wanted:
                	self.startBacklog(newShow)
        logger.log(u"Stop looking if having " + str(num_of_download) + " episode not watched", logger.DEBUG)
        return True

    def updateShows(self):
        logger.log(u"Start looking if some show need to be added to SickBeard", logger.DEBUG)
        for show in self.ShowWatchlist:
            if int(sickbeard.TRAKT_METHOD_ADD) != 2:
		self.addDefaultShow(show["tvdb_id"], show["title"], SKIPPED)
	    else:
		self.addDefaultShow(show["tvdb_id"], show["title"], WANTED)

	    if int(sickbeard.TRAKT_METHOD_ADD) == 1:
	        newShow = helpers.findCertainShow(sickbeard.showList, int(show["tvdb_id"]))
		if newShow is not None:
		    self.setEpisodeToWanted(newShow, 1, 1)
		    if not self.episode_in_watchlist(newShow.tvdbid, 1, 1):
		        if not self.update_watchlist("episode", "add", newShow.tvdbid, 1, 1):
                            return False
		    self.startBacklog(newShow)
		else:
		    self.todoWanted.append((int(show["tvdb_id"]), 1, 1))
	    self.todoWanted.append((int(show["tvdb_id"]), -1, -1)) #used to pause new shows if the settings say to
        logger.log(u"Stop looking if some show need to be added to SickBeard", logger.DEBUG)

    def updateEpisodes(self):
        """
        Sets episodes to wanted that are in trakt watchlist
        """
        logger.log(u"Start looking if some episode in WatchList has to be set WANTED", logger.DEBUG)
        for show in self.EpisodeWatchlist:
#            self.addDefaultShow(show["tvdb_id"], show["title"], SKIPPED)
            newShow = helpers.findCertainShow(sickbeard.showList, int(show["tvdb_id"]))
            for episode in show["episodes"]:
                if newShow is not None:
        	    epObj = newShow.getEpisode(int(episode["season"]), int(episode["number"]))
		    if epObj.status != WANTED:
                    	self.setEpisodeToWanted(newShow, episode["season"], episode["number"])
		    	if not self.episode_in_watchlist(newShow.tvdbid, episode["season"], episode["number"]):
		        	if not self.update_watchlist("episode", "add", newShow.tvdbid, episode["season"], episode["number"]):
                                    return False
                else:
                    self.todoWanted.append((int(show["tvdb_id"]), episode["season"], episode["number"]))
            self.startBacklog(newShow)
        logger.log(u"Stop looking if some episode in WatchList has to be set WANTED", logger.DEBUG)

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
	if not self.show_in_watchlist(tvdbid):
	    logger.log(u"Show: tvdb_id " + str(tvdbid) + ", Title " +  str(name) + " should be added to watchlist", logger.DEBUG)
	    if not self.update_watchlist("show", "add", tvdbid, 0, 0):
                return False

    def setEpisodeToArchived(self, show, s, e):
        """
        Sets an episode to archived, only is it is currently skipped or Downloadable
        """
        epObj = show.getEpisode(int(s), int(e))
        if epObj == None:
            return
        with epObj.lock:
            if epObj.status not in (SKIPPED, DOWNLOADABLE, FAILED):
                return
            logger.log(u"Setting episode s"+str(s)+"e"+str(e)+" of show " + show.name + " to archived")

            epObj.status = ARCHIVED
            epObj.saveToDB()


    def setEpisodeToWanted(self, show, s, e):
        """
        Sets an episode to wanted, only is it is currently skipped or Downloadable
        """
        epObj = show.getEpisode(int(s), int(e))
        if epObj == None:
            return
        with epObj.lock:
            if epObj.status not in (SKIPPED, DOWNLOADABLE, FAILED):
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
            if episode[1] == -1 and sickbeard.TRAKT_START_PAUSED:
                show.paused = 1
                continue
            self.setEpisodeToWanted(show, episode[1], episode[2])
	    if not self.episode_in_watchlist(show.tvdbid, episode[1], episode[2]):
	        if not self.update_watchlist("episode", "add", show.tvdbid,  episode[1], episode[2]):
                    return False
            self.todoWanted.remove(episode)
        self.startBacklog(show)

    def startBacklog(self, show):
        segments = [i for i in self.todoBacklog if i[0] == show]
        for segment in segments:
            cur_backlog_queue_item = search_queue.BacklogQueueItem(show, segment[1])
            sickbeard.searchQueueScheduler.action.add_item(cur_backlog_queue_item)
            logger.log(u"Starting backlog for " + show.name + " season " + str(segment[1]) + " because some eps were set to wanted")
            self.todoBacklog.remove(segment)

    def show_full_wathced (self, show):

	logger.log(u"Checking if show: tvdb_id " + str(show.tvdbid) + ", Title " + str(show.name) + " is completely watched", logger.DEBUG)

	found = False

	for pshow in self.ShowProgress:
	   if int(pshow["show"]["tvdb_id"]) == int(show.tvdbid) and int(pshow["progress"]["percentage"]) == 100:
		found=True
		break

	return found
	
    def update_watchlist (self, type, update, tvdb_id, s, e):

	if type=="episode":
	    # traktv URL parameters
	    data = {
		'tvdb_id': tvdb_id,
		'episodes': [ {
			'season': s,
			'episode': e
			} ]
		}
	    if update=="add" and sickbeard.TRAKT_REMOVE_WATCHLIST:
        	result=TraktCall("show/episode/watchlist/%API%", sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD, data)
            elif update=="remove" and sickbeard.TRAKT_REMOVE_WATCHLIST:
	     	result=TraktCall("show/episode/unwatchlist/%API%", sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD, data)
            if not self._getEpisodeWatchlist():
                return False
	elif type=="show":
	    # traktv URL parameters
	    data = {
		'shows': [ {
		   'tvdb_id': tvdb_id
			} ]
		}
	    if update=="add"  and sickbeard.TRAKT_REMOVE_SHOW_WATCHLIST:
        	result=TraktCall("show/watchlist/%API%", sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD, data)
            elif update=="remove" and sickbeard.TRAKT_REMOVE_SHOW_WATCHLIST:
	   	result=TraktCall("show/unwatchlist/%API%", sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD, data)
            if not self._getShowWatchlist():
                return False
	else:
            logger.log(u"Error invoking update_watchlist procedure, check parameter", logger.ERROR)
	    return False

	return True
	
    def show_in_watchlist (self, tvdb_id):

	found = False

	for show in self.ShowWatchlist:
	    if show["tvdb_id"] == str(tvdb_id):
		found=True
		break

	return found
			
    def episode_in_watchlist (self, tvdb_id, s, e):

	found = False

	for show in self.EpisodeWatchlist:
        	for episode in show["episodes"]:
		    if s==episode["season"] and e==episode["number"] and show["tvdb_id"]==str(tvdb_id):
			found=True
			break
		
	return found
			
    def _num_ep_for_season(self, show, season, episode):
		
	num_ep = 0

	for curSeason in show:

		sn = int(curSeason["season"])
		ep = int(curSeason["episodes"])

		if (sn < season):
			num_ep = num_ep + (ep)
		elif (sn == season):
			num_ep = num_ep + episode
		elif (sn == 0):
			continue
		else:
			continue

	return num_ep
	
