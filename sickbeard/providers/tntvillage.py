# Author: Giovanni Borri
# Modified by gborri, https://github.com/gborri/Sick-Beard
# URL: https://github.com/gborri/Sick-Beard
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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

import re
import traceback

import sickbeard
import generic
from sickbeard.common import Quality
from sickbeard import logger
from sickbeard import tvcache
from sickbeard import show_name_helpers
from sickbeard.common import Overview 
from sickbeard.exceptions import ex
from sickbeard import clients
from lib import requests
from bs4 import BeautifulSoup
from lib.unidecode import unidecode

category_dict = {
              'Serie TV' : 29,
              'Cartoni' : 8,
              'Anime' : 7,
              'Programmi e Film TV' : 1,
              'Documentari' : 14,
             }

category_excluded = {
              'Sport' : 22,
              'Teatro' : 23,
              'Video Musicali' : 21,
              'Film' : 4,
              'Musica' : 2,
              'Students Releases' : 13,
              'E Books' : 3,
              'Linux' : 6,
              'Macintosh' : 9,
              'Windows Software' : 10,
              'Pc Game' : 11,
              'Playstation 2' : 12,
              'Wrestling' : 24,
              'Varie' : 25,
              'Xbox' : 26,
              'Immagini sfondi' : 27,
              'Altri Giochi' : 28,
              'Fumetteria' : 30,
              'Trash' : 31,
              'PlayStation 1' : 32,
              'PSP Portable' : 33,
              'A Book' : 34,
              'Podcast' : 35,
              'Edicola' : 36,
              'Mobile' : 37,
             }

class TNTVillageProvider(generic.TorrentProvider):

    urls = {'base_url' : 'http://forum.tntvillage.scambioetico.org',
            'login' : 'http://forum.tntvillage.scambioetico.org/index.php?act=Login&CODE=01',
            'detail' : 'http://forum.tntvillage.scambioetico.org/index.php?showtopic=%s',
            'search' : 'http://forum.tntvillage.scambioetico.org/?act=allreleases&%s',
	    'search_page' : 'http://forum.tntvillage.scambioetico.org/?act=allreleases&st={0}&{1}',
            'download' : 'http://forum.tntvillage.scambioetico.org/index.php?act=Attach&type=post&id=%s',
            }

    def __init__(self):

        generic.TorrentProvider.__init__(self, "TNTVillage")

        self.supportsBacklog = True

        self.cache = TNTVillageCache(self)

	self.categories = "cat=29"

        self.url = self.urls['base_url']

        self.session = None

    def isEnabled(self):
        return sickbeard.TNTVILLAGE

    def imageName(self):
        return 'tntvillage-5.png'

    def getQuality(self, item):

        quality = Quality.sceneQuality(item[0])
        return quality    

    def _doLogin(self):

        login_params = {'UserName': sickbeard.TNTVILLAGE_USERNAME,
                        'PassWord': sickbeard.TNTVILLAGE_PASSWORD,
                        'CookieDate': 1,
                        'submit': 'Connettiti al Forum',
                        }

        self.session = requests.Session()

        try:
            response = self.session.post(self.urls['login'], data=login_params, timeout=30)
        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError), e:
            logger.log(u'Unable to connect to ' + self.name + ' provider: ' +ex(e), logger.ERROR)
            return False

        if re.search('Sono stati riscontrati i seguenti errori', response.text) \
        or re.search('<title>Connettiti</title>', response.text) \
        or response.status_code == 401:
            logger.log(u'Invalid username or password for ' + self.name + ' Check your settings', logger.ERROR)       
            return False

        return True

    def _get_season_search_strings(self, show, season=None):

        search_string = {'Episode': []}

        if not show:
            return []

        seasonEp = show.getAllEpisodes(season)

        wantedEp = [x for x in seasonEp if show.getOverview(x.status) in (Overview.WANTED, Overview.QUAL)]          

        #If Every episode in Season is a wanted Episode then search for Season first
        if wantedEp == seasonEp and not show.air_by_date:
            search_string = {'Season': [], 'Episode': []}
            for show_name in set(show_name_helpers.allPossibleShowNames(show)):
                ep_string = show_name +' S%02d' % int(season) #1) ShowName SXX   
                search_string['Season'].append(ep_string)

        #Building the search string with the episodes we need         
        for ep_obj in wantedEp:
            search_string['Episode'] += self._get_episode_search_strings(ep_obj)[0]['Episode']

        #If no Episode is needed then return an empty list
        if not search_string['Episode']:
            return []

        return [search_string]

    def sanitizeSceneName_not_dotted(self, epname, ezrss=False):
    	"""
    	Takes a show name and returns the "scenified" version of it.

    	ezrss: If true the scenified version will follow EZRSS's cracksmoker rules as best as possible

    	Returns: A string containing the scene version of the show name given.
    	"""

    	if not ezrss:
        	bad_chars = u",:()'!?\u2019"
    	# ezrss leaves : and ! in their show names as far as I can tell
   	else:
        	bad_chars = u",()'?\u2019"

    	# strip out any bad chars
    	for x in bad_chars:
        	epname = epname.replace(x, "")

    	# tidy up stuff that doesn't belong in scene names
    	epname = epname.replace("- ", "").replace("&", "and").replace('/', '.')
    	epname = re.sub("\.\.*", ".", epname)

    	if epname.endswith('.'):
        	epname = epname[:-1]

    	return epname

    def _get_episode_search_strings(self, ep_obj):

        search_string = {'Episode': []}

        if not ep_obj:
            return []

        if ep_obj.show.air_by_date:
            for show_name in set(show_name_helpers.allPossibleShowNames(ep_obj.show)):

                ep_string = show_name_helpers.sanitizeSceneName(show_name) +' '+ str(ep_obj.airdate)
		if not search_string['Episode']:
                	search_string['Episode'].append(ep_string)

		found = 0
		for ep_name in search_string['Episode']:
			if ep_string == ep_name:
				found = 1	
				continue
		if not found:
             		search_string['Episode'].append(ep_string)

                ep_string = self.sanitizeSceneName_not_dotted(show_name) +' '+ str(ep_obj.airdate)

		found = 0
		for ep_name in search_string['Episode']:
			if ep_string == ep_name:
				found = 1	
				continue
		if not found:
                	search_string['Episode'].append(ep_string)
        else:
            for show_name in set(show_name_helpers.allPossibleShowNames(ep_obj.show)):

                ep_string = show_name_helpers.sanitizeSceneName(show_name) +' '+ \
                sickbeard.config.naming_ep_type[2] % {'seasonnumber': ep_obj.season, 'episodenumber': ep_obj.episode}
		if not search_string['Episode']:
                	search_string['Episode'].append(ep_string)

		found = 0
		for ep_name in search_string['Episode']:
			if ep_string == ep_name:
				found = 1	
				continue
		if not found:
             		search_string['Episode'].append(ep_string)

                ep_string = self.sanitizeSceneName_not_dotted(show_name) +' '+ \
                sickbeard.config.naming_ep_type[2] % {'seasonnumber': ep_obj.season, 'episodenumber': ep_obj.episode}

		found = 0
		for ep_name in search_string['Episode']:
			if ep_string == ep_name:
				found = 1	
				continue
		if not found:
                	search_string['Episode'].append(ep_string)

                ep_string = show_name_helpers.sanitizeSceneName(show_name) +' S%02d' % int(ep_obj.season) #1) ShowName SXX   
		found = 0
		for ep_name in search_string['Episode']:
			if ep_string == ep_name:
				found = 1	
				continue
		if not found:
                	search_string['Episode'].append(ep_string)

                ep_string = self.sanitizeSceneName_not_dotted(show_name) +' S%02d' % int(ep_obj.season) #1) ShowName SXX   
		found = 0
		for ep_name in search_string['Episode']:
			if ep_string == ep_name:
				found = 1	
				continue
		if not found:
                	search_string['Episode'].append(ep_string)


        return [search_string]

    def _reverseQuality(self, quality):

        quality_string = ''

        if quality == Quality.SDTV:
            quality_string = ' HDTV x264'
        if quality == Quality.SDDVD:
            quality_string = ' DVDRIP x264'
        elif quality == Quality.HDTV:
            quality_string = ' 720p HDTV x264'
        elif quality == Quality.FULLHDTV:
            quality_string = ' 1080p HDTV x264'
        elif quality == Quality.RAWHDTV:
            quality_string = ' 1080i HDTV mpeg2'
        elif quality == Quality.HDWEBDL:
            quality_string = ' 720p WEB-DL h264'
        elif quality == Quality.FULLHDWEBDL:
            quality_string = ' 1080p WEB-DL h264'
        elif quality == Quality.HDBLURAY:
            quality_string = ' 720p Bluray x264'
        elif quality == Quality.FULLHDBLURAY:
            quality_string = ' 1080p Bluray x264'

        return quality_string

    def _episodeQuality(self,torrent_rows):
   	"""
        Return The quality from the scene episode HTML row.
        """

	name=''

	img_all = (torrent_rows.find_all('td'))[1].find_all('img')

	for type in img_all:
	  try:

		name = name + " " + type['src'].replace("style_images/mkportal-636/","").replace(".gif","").replace(".png","")

	  except Exception, e:
          	logger.log(u"Failed parsing " + self.name + " Traceback: "  + traceback.format_exc(), logger.ERROR)

	name = name + " " + (torrent_rows.find_all('td'))[1].get_text()
	logger.log(u"full quality string:" + name, logger.DEBUG)

        checkName = lambda list, func: func([re.search(x, name, re.I) for x in list])

        if checkName(["(tv|sat|hdtv|hdtvrip|hdtvmux|webdl|webrip|web-dl|webdlmux|dlrip|dlmux|dtt|bdmux)","(xvid|h264|divx)"], all) and not checkName(["(720|1080)[pi]"], all):
            return Quality.SDTV
        elif checkName(["(dvdrip|dvdmux|dvd)"], any) and not checkName(["(720|1080)[pi]"], all) and not checkName(["(sat|tv)"], all) and not checkName(["BD"], all) and not checkName(["fullHD"], all):
            return Quality.SDDVD
        elif checkName(["720p", "(h264|xvid|divx)"], all) and not checkName(["BD"], all) and not checkName(["webdl|webrip|web-dl|webdlmux|hdtvmux|sat|dlmux"], all):
            return Quality.HDTV
        elif checkName(["720p", "(h264|xvid|divx)"], all) and not checkName(["BD"], all) and checkName(["webdl|webrip|web-dl|webdlmux|hdtvmux|sat|dlmux"], all):
            return Quality.HDWEBDL
        elif checkName(["fullHD", "(h264|xvid|divx)"], all) or checkName(["fullHD"], all) and not checkName(["BD"], all) and not checkName(["webdl|webrip|web-dl|webdlmux|hdtvmux|sat|dlmux"], all):
            return Quality.FULLHDTV
        elif checkName(["fullHD", "(h264|xvid|divx)"], all) or checkName(["fullHD"], all) and not checkName(["BD"], all) and checkName(["webdl|webrip|web-dl|webdlmux|hdtvmux|sat|dlmux"], all):
            return Quality.FULLHDWEBDL
        elif checkName(["BD", "720p", "(h264|xvid|divx)"], all) or  checkName(["BD", "h264|xvid|divx"], all) and not checkName(["fullHD"], all):
            return Quality.HDBLURAY
        elif checkName(["BD", "fullHd", "(h264|xvid|divx)"], all):
            return Quality.FULLHDBLURAY
        else:
            return Quality.UNKNOWN

    def _is_italian(self,torrent_rows):

	is_italian = 0

	name=''

	span_tag = (torrent_rows.find_all('td'))[1].find('b').find('span')

	name = str(span_tag)
	name = name.split('sub')[0] 

	if re.search("ita", name, re.I):
		logger.log(u"Found Italian Language", logger.DEBUG)
		is_italian=1

	return is_italian

    def _doSearch(self, search_params, show=None):

        results = []
        items = {'Season': [], 'Episode': [], 'RSS': []}

        self.categories = "cat=" + str(sickbeard.TNTVILLAGE_CATEGORY)

        if not self._doLogin():
            return []

        for mode in search_params.keys():
            for search_string in search_params[mode]:

                if isinstance(search_string, unicode):
                    search_string = unidecode(search_string)
		
		try: 	

			last_page=0
			y=int(sickbeard.TNTVILLAGE_PAGE)

			for x in range(0,y):
				
				z=x*20
                		if last_page:
					break	

				logger.log(u"Page: " + str(x) + " of " + str(y), logger.DEBUG)

   	    			if mode != 'RSS':
					searchURL = (self.urls['search_page'] + '&filter={2}').format(z,self.categories,search_string)
        			else:
					searchURL = self.urls['search_page'].format(z,self.categories)

                		logger.log(u"Search string: " + searchURL, logger.DEBUG)

                		data = self.getURL(searchURL)
                		if not data:
                    			continue

                		try:
                    			html = BeautifulSoup(data, features=["html5lib", "permissive"])

                    			torrent_table = html.find('table', attrs = {'class' : 'copyright'})
                    			torrent_rows = torrent_table.find_all('tr') if torrent_table else []

                    			#Continue only if one Release is found
					a=len(torrent_rows)
					logger.log(u"Num of Row: "+ str(a), logger.DEBUG)
                    			if len(torrent_rows)<3:
                        			logger.log(u"The Data returned from " + self.name + " do not contains any torrent", logger.DEBUG)
						last_page=1
                        			continue
					if a < 42:
						 last_page=1

                    			for result in torrent_table.find_all('tr')[2:]:

                        			try:
                            				link = result.find('td').find('a')
                            				title = link.string
                            				id = ((result.find_all('td')[8].find('a'))['href'])[-8:]
                            				download_url = self.urls['download'] % (id)
                            				leechers = result.find_all('td')[3].find_all('td')[1].text
			    				leechers = int(leechers.strip('[]'))
                            				seeders = result.find_all('td')[3].find_all('td')[2].text
			    				seeders = int(seeders.strip('[]'))

                        			except AttributeError:
                            				continue

                        			if mode != 'RSS' and seeders == 0:
                            				continue 

                        			if not title or not download_url:
                            				continue

						title = title.replace(" Versione 720p","").replace(" Versione 1080p","") + self._reverseQuality(self._episodeQuality(result))

                        			item = title, download_url, id, seeders, leechers
                        			logger.log(u"Found result: " + title + "(" + searchURL + ")", logger.DEBUG)

						if not self._is_italian(result) and not sickbeard.TNTVILLAGE_SUBTITLE:
                        				logger.log(u"Subtitled, Skipped", logger.DEBUG)
							continue
						else:
                        				logger.log(u"Not Subtitled or Forced, Got It!", logger.DEBUG)
							

                        			items[mode].append(item)

                		except Exception, e:
                    			logger.log(u"Failed parsing " + self.name + " Traceback: "  + traceback.format_exc(), logger.ERROR)

		except Exception, e: 
			logger.log(u"Failed parsing " + self.name + " Traceback: "  + traceback.format_exc(), logger.ERROR)

            	#For each search mode sort all the items by seeders
            	items[mode].sort(key=lambda tup: tup[3], reverse=True)        

            	results += items[mode]  

        return results

    def _get_title_and_url(self, item):

        title, url, id, seeders, leechers = item

        if url:
            url = str(url).replace('&amp;','&')

        return (title, url)

    def getURL(self, url, headers=None):

        if not self.session:
            self._doLogin()

        if not headers:
            headers = []

        try:
            response = self.session.get(url, verify=False)
        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError), e:
            logger.log(u"Error loading "+self.name+" URL: " + ex(e), logger.ERROR)
            return None

        if response.status_code != 200:
            logger.log(self.name + u" page requested with url " + url +" returned status code is " + str(response.status_code) + ': ' + clients.http_error_code[response.status_code], logger.WARNING)
            return None

        return response.content
       
class TNTVillageCache(tvcache.TVCache):

    def __init__(self, provider):

        tvcache.TVCache.__init__(self, provider)

        # only poll TNTVillage every 30 minutes max
        self.minTime = 5

    def updateCache(self):

        if not self.shouldUpdate():
            return

        search_params = {'RSS': ['']}
        rss_results = self.provider._doSearch(search_params)
        
        if rss_results:
            self.setLastUpdate()
        else:
            return []
        
        logger.log(u"Clearing " + self.provider.name + " cache and updating with new information")
        self._clearCache()

        for result in rss_results:
            item = (result[0], result[1])
            self._parseItem(item)

    def _parseItem(self, item):

        (title, url) = item

        if not title or not url:
            return

        logger.log(u"Adding item to cache: " + title, logger.DEBUG)

        self._addCacheEntry(title, url)

provider = TNTVillageProvider()
