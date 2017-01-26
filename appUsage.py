import requests
import sys
import xml.etree.ElementTree as ET
import plotly as py
import plotly.offline as offline
import datetime
import calendar

# JSS INFO
jss_host = "https://jss.com"
jss_port = 8443
jss_path = ""

# User needs rights to read/update the static groups and read devices.
jss_username = "API_Account"
jss_password = "potato"


# Would like to pass this as an arg later
labs = ['AS-LAB*',
'GW-Student-Lab*',
'IKE-Student-MediaLab*',
'IKE-Student-Lab307*',
'MB-Student-Lab-MML*',
'TG-RoyalLab-*',
'NJH-213*',
'NJH-301Lab*',
'WJH-Student-607*',
'WJH-Student-611*',
'HHS-Student-S152*',
'HHS-Student-S175*',
'HHS-Student-S184*',
'HHS-Student-S200*',
'HHS-Student-W161*',
'HHS-Student-W188*',
'HHS-Student-W221*',
'HHS-Student-W252*']


# Calculate the date range for the last full month
now = datetime.datetime.now()
# Get today's day of month
days_in_month = int(now.strftime('%d'))
# Subtract day of month from now to get last month
last_month = now - datetime.timedelta(days = days_in_month)
startdate = '%s-01' %last_month.strftime('%Y-%m')
enddate = '%s-%s' %(last_month.strftime('%Y-%m'),calendar.monthrange(int(last_month.strftime('%Y')),int(last_month.strftime('%m')))[1])

# HTML Filename
filename = '/var/www/html/labs/test_lab_usage_%s_%s.html' % (startdate,enddate)

# How many apps per lab do you want in each chart:
apps_per_lab = 5

# Put all web browsers together
web_browsers=['Safari.app',
'Firefox.app',
'Safari 2.app',
'Google Chrome.app']


# This will from a list of colors and then once the list is exhausted, it will chose at random
avail_colors = ['rgb(166,206,227)',
				'rgb(31,120,180)',
				'rgb(178,223,138)',
				'rgb(251,154,153)',
				'rgb(227,26,28)',
				'rgb(253,191,111)',
				'rgb(255,127,0)',
				'rgb(202,178,214)',
				'rgb(106,61,154)',
				'rgb(141,211,199)',
				'rgb(255,255,179)',
				'rgb(190,186,218)',
				'rgb(251,128,114)',
				'rgb(128,177,211)',
				'rgb(253,180,98)',
				'rgb(179,222,105)',
				'rgb(252,205,229)',
				'rgb(217,217,217)',
				'rgb(188,128,189)',
				'rgb(176,23,31)',
				'rgb(132,112,255)',
				'rgb(110,123,139)',
				'rgb(152,245,255)',
				'rgb(124,252,0)',
				'rgb(255,246,143)',
				'rgb(255,165,0)',
				'rgb(255,127,80)',
				'rgb(188,143,143)']

# Stick with green for web browser color
web_browser_color = 'rgb(51,160,44)'

# Filter out these apps
exclude=['Composer.app',
'CoreServicesUIAgent.app',
'SystemUIServer.app',
'Sophos Anti-Virus.app',
'Keychain Circle Notification.app',
'plugin-container.app',
'TMHelperAgent.app',
'loginwindow.app',
'jamfHelper.app',
'WiFiAgent.app',
'CoreLocationAgent.app',
'ScreenSaverEngine.app',
'crashreporter.app',
'SecurityAgent.xpc',
'SecurityAgent.bundle',
'Locked',
'com.apple.dock.extra.xpc',
'NotificationCenter.app',
'Finder.app',
'GoogleSoftwareUpdateAgent.app',
'cloudphotosd.app',
'nbagent.app',
'com.apple.WebKit.Plugin.64.xpc',
'com.apple.WebKit.WebContent.xpc',
'LaterAgent.app',
'AirPlayUIAgent.app',
'SophosUIServer.app',
'Bluetooth Setup Assistant.app',
'.app',
'\\.app',
'Adobe Flash Player Install Manager.app',
'App Store.app',
'EasyInteractiveDriver.app',
'System Preferences.app',
'UnmountAssistantAgent.app',
'EscrowSecurityAlert.app'
]


def getComputers(computerlab):
	'''Returns a list of serial numbers from a match search term'''
	# Computer lab is the search term from the lab list

	# Make the request from the JSS for a list of devices
	r = requests.get(jss_host + ':' + str(jss_port) + jss_path + '/JSSResource/computers/match/' + computerlab , headers={'Accept': 'application/xml'}, auth=(jss_username,jss_password))
	try:
		r.raise_for_status()
	except requests.exceptions.HTTPError as e:
		# Maybe set up for a retry, or continue in a retry loop
		print e.message
		if r.status_code == 401:
			print "Incorrect Username, Password or insufficient rights."
		sys.exit(1)

	tree = ET.fromstring(r.content)
	itemsFromJSS = []
	for item in tree.findall('computer'):
		itemsFromJSS.append(item.find('serial_number').text)
	return itemsFromJSS


def getUsage(computers):
	'''Get's the usage for the time period for an individual unit
	the results are appended to a dictionary that is created for each lab
	'''

	app_usage = {}

	for serial_number in computers:
		# Making the connection and getting the app usage
		r = requests.get(jss_host + ':' + str(jss_port) + jss_path + '/JSSResource/computerapplicationusage/serialnumber/' + serial_number + "/" + startdate + "_" + enddate , headers={'Accept': 'application/xml'}, auth=(jss_username,jss_password))
		try:
			r.raise_for_status()
		except requests.exceptions.HTTPError as e:
			# Maybe set up for a retry, or continue in a retry loop
			print e.message
			if r.status_code == 401:
				print "Incorrect Username, Password or insufficient rights."
			sys.exit(1)

		root = ET.fromstring(r.content)
		for c in root.findall('usage/apps/app'):
			foreground_time = c.find('foreground').text
			app_name = c.find('name').text
			# Check the exclude list
			if app_name not in exclude and app_name not in web_browsers:
				try:
					# Attempt to add time to existing key pair
					app_usage[app_name] = app_usage.get(app_name) + int(foreground_time)
				except:
					# Key pair didn't exist, start it
					app_usage[app_name] = int(foreground_time)

			if app_name in web_browsers:

				try:
					# Attempt to add time to existing key pair
					app_usage["Web Broswers"] = app_usage.get("Web Broswers") + int(foreground_time)
				except:
					# Key pair didn't exist, start it
					app_usage["Web Broswers"] = int(foreground_time)


	return app_usage


def sort_apps(app_usage):
	'''Sorts apps so we can get the top five'''
	import operator
	sortedappsusage = sorted(app_usage.items(), key=operator.itemgetter(1))
	# Flip the order so largest is on top
	sortedappsusage.reverse()
	return sortedappsusage


def makePieandCSV(lab,computers,sorted_apps):
	'''Need plotly installed
	Takes sorted apps and makes pies
	Each app name will get its own unique color
	'''

	# This is what we use to determine where we are in the list of available colors
	global color_count

	# Start lists for pie values, labels, colors
	labels = []
	values = []
	colors = []

	i = 1

	# Generate the values for the file and the pie
	for sortedapp in sorted_apps:
		if i > apps_per_lab:
			break
		if sortedapp[1] < 100:
			continue
		i = i + 1
		#print i,": ",sortedapp[0],":",sortedapp[1] / len(computers)
		labels.append(sortedapp[0])
		values.append(sortedapp[1])



		try:
			app_colors[sortedapp[0]]
			colors.append(app_colors[sortedapp[0]])
			print app_colors.get(sortedapp[0])
			print app_colors[sortedapp[0]]
		except:


			if color_count >= len(app_colors):
				import random
				#colors.append(('rgb(%s,%s,%s)' % (random.randint(0,255),random.randint(0,255),random.randint(0,255))))
				app_colors[sortedapp[0]] = ('rgb(%s,%s,%s)' % (random.randint(0,255),random.randint(0,255),random.randint(0,255)))
			else:
				app_colors[sortedapp[0]] = avail_colors[color_count]


			colors.append(app_colors[sortedapp[0]])

			print "New Color Assigned: %s" % app_colors.get(sortedapp[0])
			color_count = color_count + 1


	# Write the values to disk
	with open('%s_data.txt' % filename,'a') as f:
		for label,value in zip(values,labels):
			f.writelines("'%s','%s','%s','%s'\n" % (lab,len(computers),label,value))
		f.close


	# Make the pie data dict
	pie_data = {
		'data': [{'labels': labels,
				  'values': values,
				  'name': lab,
				  'marker': {'colors': colors},
				  'type': 'pie',
				  'hoverinfo':'label+percent+name+value',
				  'textinfo':'percentage'}],
		'layout': {'title': lab}
		 }

	# Add the annotations
	pie_data['layout']['annotations'] = [
	{
		"font": {
			"size": 14
		},
		"showarrow": False,
		"text": "Amount of time in active application: %s hours" % round(( sum(values) / float(60)),2),
		"x": .7,
		"y": -.2
	}]

	# Append the pie object (div) to pies
	pies.append(offline.plot(pie_data,output_type='div',include_plotlyjs=False,show_link=False))


def build_html():
	'''Write Head, all pies, and close to a file'''

	# Imports the javascript library
	html_head = '''<html>
	<head>	<style>
	.pietime {
		width:50%;
		height:50%;
		float:left;
		}
	</style>
	<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
	</head>
	<body>'''

	title_line = '''<h1>Lab Report for {0} to {1}</h1>
	<h4>Showing usage for any Application over 100 total minutes</h4>
	<h4>All time values are the aggregate for the lab</h4>'''.format(startdate,enddate)


	div_wrapper_a = '''<div id='wrapper' class='pietime'>'''
	div_wrapper_b = '''</div>'''

	html_close = '''
	</body>
	</html>'''

	with open(filename, 'w') as f:
		f.write(html_head)
		f.write(title_line)
		for pie in pies:
			f.write(div_wrapper_a)
			f.write(pie)
			f.write(div_wrapper_b)
		f.write(html_close)
		f.close()


def main():

	# Run over all labs
	for lab in labs:

		# Get computers using match term
		computers = getComputers(lab)

		# Check length incase of bad search term
		if len(computers) == 0:
			print "+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
			print " WARNING "
			print " %s not found " % lab

		# Get app usage per device
		app_usage = getUsage(computers)

		# Sort the app usage so the pies look goooood
		sorted_apps = sort_apps(app_usage)

		# Add the div to the pies list and write to a csv for further analysis.
		makePieandCSV(lab,computers,sorted_apps)

	# Write to HTML file for that month
	build_html()


if __name__ == '__main__':
	# Used for list position in avail_colors - could maybe use the pop function on list
	color_count = 0

	# Store the app name and color selected
	app_colors = {}

	# Add our special green for web browsers
	app_colors["Web Broswers"] = web_browser_color

	# List of pie charts for the build_html function
	pies = []

	# Let's go!
	main()
