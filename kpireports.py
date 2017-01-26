import requests
import sys
import xml.etree.ElementTree as ET
import datetime
import plotly.offline as offline
import os
import pymysql
import plotly.plotly as py # do I really need this for the bar chart?
import plotly.graph_objs as go
import logging

logging.basicConfig(filename="/home/administrator/Scripts/kpireport/kpireports.log",
					level=logging.INFO,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',)


# Report location
HTML_FILENAME = '/var/www/html/kpis/latest.html'

## Device Check-in Section Settings
# JSS INFO
JSS_HOST = "https://jamf.pro.org"
JSS_PORT = 8443
JSS_PATH = ""

# User needs rights to read/update the static groups and read devices.
JSS_API_USERNAME = "API_Account"
JSS_API_PASSWORD = "potato"

# If you'd like to excluded a building, add it here
JSS_EXCLUDED_BUILDINGS = ('Recycled','Stolen','Stored Inventory')

# Setup time frames for checkins
JSS_CHECKIN_LONG_TERM = datetime.datetime.now() - datetime.timedelta(31)
JSS_CHECKIN_SHORT_TERM = datetime.datetime.now() - datetime.timedelta(14)

## Web Help Desk Report Settings
# When do you want the report to go back to?
WHD_BEGINNING_DATE = datetime.datetime(2016,8,15)

# Web Help Desk Setup -API for On-time vs Past-due report. Database connection for survey results
WHD_HOST_NAME = 'help.company.com'
WHD_SSH_USERNAME = 'ssh_username'
WHD_SSH_PASSWORD = 'potato'
WHD_DATABASE_USER = 'database_username'
WHD_DATABASE_PASSWORD = 'potato'
WHD_DATABASE_NAME = 'whd'
WHD_ADMIN_USERNAME = 'admin'
WHD_API_KEY = 'aksdf;lkjasdfl;kjasldkfja;lsdkfja;lsdkfj'


class JSSDeviceReport:
	"""Setup the Pie Object for device checkins KPI"""
	def __init__(self):
		self.building_report = {}
		self.jss_build_buildings_report()
		self.all_buildings_report = self.jss_build_all_buildings_report()
		self.sorted_building_report = self.jss_sort_building_report()

	def jss_build_buildings_report(self):
		"""Runs the function to download all serials from the JSS and determine whether or
		 not a device is checking in short term or long term"""
		self.jss_get_devices_by_type('computer','report_date_epoch',0,1,2,3)
		self.jss_get_devices_by_type('mobile_device','last_inventory_update_epoch',4,5,6,7)


	def jss_get_devices_by_type(self,device_type,lastcheckin,a,b,c,d):
		"""Builds the building_report dictionary which is a dictionary of lists
		The key is the building name and there are 8 values.
		Computers are in the first four, Mobile devices in the last four.
		Check in Short Term True,False,Long Term, False"""

		# Modify the search depending on device type
		if device_type == 'computer':
			api_path = '/JSSResource/computers/subset/basic'
		else:
			api_path = '/JSSResource/mobiledevices/subset/basic'

		r = requests.get(JSS_HOST + ':' + str(JSS_PORT) + JSS_PATH + api_path, headers={'Accept': 'application/xml'}, auth=(JSS_API_USERNAME,JSS_API_PASSWORD))
		try:
			r.raise_for_status()
		except requests.exceptions.HTTPError as e:
			# Maybe set up for a retry, or continue in a retry loop
			logging.error(e.message)
			if r.status_code == 401:
				logging.error("Incorrect Username, Password or insufficient rights.")
			sys.exit(1)

		# We need this section because the time is not provided in the previous query and the building name isn't in the following query
		if device_type == 'mobile_device':
			md_serials_buildings = {}
			mdr = requests.get(JSS_HOST + ':' + str(JSS_PORT) + JSS_PATH + '/JSSResource/mobiledevices/match/*', headers={'Accept': 'application/xml'}, auth=(JSS_API_USERNAME,JSS_API_PASSWORD))
			xml_md_tree = ET.fromstring(mdr.content)
			for item in xml_md_tree.findall(device_type):
				md_serials_buildings[item.find('serial_number').text] = item.find('building_name').text

		xml_tree = ET.fromstring(r.content)
		for item in xml_tree.findall(device_type):

			if device_type == 'mobile_device':
				building = md_serials_buildings[item.find('serial_number').text]

			else:
				building = item.find('building').text

			if building in JSS_EXCLUDED_BUILDINGS:
				"print excluded %s " % building
				continue
			try:
				building

				try:
					self.building_report[building]

				except:
					self.building_report[building] = [0,0,0,0,0,0,0,0]

				if datetime.datetime.utcfromtimestamp(int(item.find(lastcheckin).text) / 1000) > JSS_CHECKIN_SHORT_TERM:
					self.building_report[building][a] = self.building_report[building][a] + 1

				else:
					self.building_report[building][b] = self.building_report[building][b] + 1

				if datetime.datetime.utcfromtimestamp(int(item.find(lastcheckin).text) / 1000) > JSS_CHECKIN_LONG_TERM:
					self.building_report[building][c] = self.building_report[building][c] + 1
				else:
					self.building_report[building][d] = self.building_report[building][d] + 1
			except:
				pass


	def jss_sort_building_report(self):
		"""Sorts the self.building_report so the pies come out in alpha order by building name"""
		import operator
		sorted_building_report = sorted(self.building_report.items(), key=operator.itemgetter(0))
		return sorted_building_report


	def jss_build_all_buildings_report(self):
		"""Adds up everything in the building reports to generate the all_buildings pie"""
		all_buildings = [0,0,0,0,0,0,0,0]
		for k,v in self.building_report.iteritems():
			for i in range(0,8):
				all_buildings[i] = all_buildings[i] + v[i]
		print all_buildings
		return all_buildings


class WHDSurveyReport():
	def __init__(self):
		self.server = self.whd_create_tunnel()
		self.server.start()
		self.csat = ''
		self.survey_time_to_close = ''
		self.monthly_time_to_close = ''
		self.monthly_csat = ''
		self.whd_run_mysql_queries()
		self.server.close()


	def whd_create_tunnel(self):
		'''Make the SSH Tunnel to encrypt the MySQL queries'''
		from sshtunnel import SSHTunnelForwarder
		try:
			server = SSHTunnelForwarder(
			WHD_HOST_NAME,
			ssh_username=WHD_SSH_USERNAME,
			ssh_password=WHD_SSH_PASSWORD,
			remote_bind_address=('127.0.0.1',3306),
			local_bind_address=('0.0.0.0', 13306)
			)
		except:
			logging.error('Something went wrong with the tunnel')
			sys.exit(1)
		return server


	def whd_run_mysql_queries(self):
		'''Connect to WHD and run the MySQL Queries'''

		csat_average_query = """select AVG(SURVEY_QUESTION_RESPONSE.SELECTION)
			from SURVEY_RESPONSE
			join SURVEY_QUESTION_RESPONSE
			on SURVEY_RESPONSE.ID=SURVEY_QUESTION_RESPONSE.SURVEY_RESPONSE_ID
			where SURVEY_ID = 3
			and RESPONSE_DATE > '{}'
			and SURVEY_QUESTION_RESPONSE.SURVEY_QUESTION_ID = 8""".format(WHD_BEGINNING_DATE)

		survey_time_to_close_query = """select AVG(SURVEY_QUESTION_RESPONSE.SELECTION)
			from SURVEY_RESPONSE
			join SURVEY_QUESTION_RESPONSE
			on SURVEY_RESPONSE.ID=SURVEY_QUESTION_RESPONSE.SURVEY_RESPONSE_ID
			where SURVEY_ID = 3
			and RESPONSE_DATE > '{}'
			and SURVEY_QUESTION_RESPONSE.SURVEY_QUESTION_ID = 10""".format(WHD_BEGINNING_DATE)

		monthly_csat_average_query = """select AVG(SURVEY_QUESTION_RESPONSE.SELECTION),YEAR(RESPONSE_DATE),MONTH(RESPONSE_DATE)
			from SURVEY_RESPONSE
			join SURVEY_QUESTION_RESPONSE
			on SURVEY_RESPONSE.ID=SURVEY_QUESTION_RESPONSE.SURVEY_RESPONSE_ID
			where SURVEY_ID = 3 and RESPONSE_DATE > '{}'
			and SURVEY_QUESTION_RESPONSE.SURVEY_QUESTION_ID = 8
			group by YEAR(RESPONSE_DATE), MONTH(RESPONSE_DATE)""".format(WHD_BEGINNING_DATE)

		montly_survey_time_to_close_query = """select AVG(SURVEY_QUESTION_RESPONSE.SELECTION),YEAR(RESPONSE_DATE),MONTH(RESPONSE_DATE)
		from SURVEY_RESPONSE
		join SURVEY_QUESTION_RESPONSE
		on SURVEY_RESPONSE.ID=SURVEY_QUESTION_RESPONSE.SURVEY_RESPONSE_ID
		where SURVEY_ID = 3
		and RESPONSE_DATE > '{}'
		and SURVEY_QUESTION_RESPONSE.SURVEY_QUESTION_ID = 10
		group by YEAR(RESPONSE_DATE), MONTH(RESPONSE_DATE)""".format(WHD_BEGINNING_DATE)

		whd_this_month_queries = [csat_average_query,survey_time_to_close_query]
		whd_all_month_queries = [monthly_csat_average_query,montly_survey_time_to_close_query]

		values = [0,0,0,0]

		try:
			connect_to_db = pymysql.connect( host='127.0.0.1', port=13306, user=WHD_DATABASE_USER, passwd=WHD_DATABASE_PASSWORD, db=WHD_DATABASE_NAME )

		except:
			try:
				# Try one more time just in case
				connect_to_db = pymysql.connect( host='127.0.0.1', port=13306, user=WHD_DATABASE_USER, passwd=WHD_DATABASE_PASSWORD, db=WHD_DATABASE_NAME )
			except MySQLError as e:
				logging.error('Got error {!r}, errno is {}'.format(e, e.args[0]))
				sys.exit(1)
		i = 0
		for query in whd_this_month_queries:
			cursor = connect_to_db.cursor()
			response = cursor.execute(query.strip())
			data = cursor.fetchone()
			values[i] = float(data[0])
			i += 1

		for query in whd_all_month_queries:
			cursor = connect_to_db.cursor()
			response = cursor.execute(query.strip())
			values[i] = cursor.fetchall()
			i += 1

		self.csat = values[0]
		self.survey_time_to_close = values[1]
		self.monthly_csat = values[2]
		self.monthly_time_to_close = values[3]


class WHDOTvsPDReport():
	def __init__(self):
		self.tickets = []
		self.timestamps = []
		self.whd_get_all_closed_tickets()
		self.byTech = {}
		self.byLocation = {}
		self.byDate = {}
		self.nonTechTickets = 0
		self.TechTickets = 0
		self.whd_get_ticket_data()
		self.on_time_summary,self.past_due_summary = self.summarize_report()


	def whd_get_all_closed_tickets(self):
		"""Get all tickets before a certain date"""
		end = 1
		page = 1
		while end == 1:
			ticket_list_r = requests.get("https://" + WHD_HOST_NAME + "/helpdesk/WebObjects/Helpdesk.woa/ra/Tickets.xml?qualifier=(statustype.statusTypeName %3D 'Closed')&page=" + str(page) + "&username=" + WHD_ADMIN_USERNAME + "&apiKey=" + WHD_API_KEY)
			closed_tickets_xml = ET.fromstring(ticket_list_r.content)
			for item in closed_tickets_xml.findall('Ticket'):
					if datetime.datetime.strptime(item.find('lastUpdated').text, '%Y-%m-%dT%H:%M:%SZ') > WHD_BEGINNING_DATE:
						self.tickets.append(item.get('id'))
						self.timestamps.append(item.find('lastUpdated').text)
					else:
						end = 0
						print "Done"
						break
			page += 1 # go to next page of devices until we hit the stop date


	def whd_get_ticket_data(self):
		"""Loop over tickets to determine if they are on time or not"""
		for ticket in self.tickets:
			status = 0 # Setting this for while loop to make sure we only set ontime/pastdue once.
			while status == 0:
# 				print "Working on Ticket: %s" % ticket
				single_ticket_r = requests.get("https://" + WHD_HOST_NAME + "/helpdesk/WebObjects/Helpdesk.woa/ra/Tickets/" + str(ticket) + ".xml?username=" + WHD_ADMIN_USERNAME + "&apiKey=" + WHD_API_KEY)
				single_ticket_xml = ET.fromstring(single_ticket_r.content)

				# Check if it is a tech ticket
				if single_ticket_xml.find('problemtype/detailDisplayName').text.split(';')[0] == 'Technology & Media &#8226' and datetime.datetime.strptime(single_ticket_xml.find('closeDate').text, '%Y-%m-%dT%H:%M:%SZ') > WHD_BEGINNING_DATE:
					self.TechTickets = self.TechTickets + 1

					# Test to see if location is set otherwise set to "No Location"
					try:
						location = single_ticket_xml.find('location').attrib.get('id')
					except:
						location = "No Location"

					closedate = datetime.datetime.strptime(single_ticket_xml.find('closeDate').text, '%Y-%m-%dT%H:%M:%SZ')
					date = closedate.strftime('%m-%Y')

					# If this is the first time we've seen this location, setup a entry in the dictionary
					try:
						self.byLocation[location]
					except:
						self.byLocation[location] = [0,0]

					# Test to see if location is set otherwise set to "No Tech"
					try:
						tech = single_ticket_xml.find('clientTech/displayName').text
					except:
						tech = "No Tech"

					# If this is the first time we've seen this date, setup a entry in the dictionary
					try:
						self.byDate[date]
					except:
						self.byDate[date] = [0,0]

					# If this is the first time we've seen this tech, setup a entry in the dictionary
					try:
						self.byTech[tech]
					except:
						self.byTech[tech] = [0,0]


					# check to see if it is on time or past due by regular check
					if datetime.datetime.strptime(single_ticket_xml.find('displayDueDate').text, '%Y-%m-%dT%H:%M:%SZ') > datetime.datetime.strptime(single_ticket_xml.find('closeDate').text, '%Y-%m-%dT%H:%M:%SZ'):
# 						print "On time and closed on time"
						self.byTech[tech][0] = self.byTech[tech][0] + 1
						self.byLocation[location][0] = self.byLocation[location][0] + 1
						self.byDate[date][0] = self.byDate[date][0] + 1
						status = 1
						continue


# 					print "Not closed on time...checking last comment"

					# if past due, try looking to last not closed note
					for item in single_ticket_xml.findall('notes/TechNote'):

						if datetime.datetime.strptime(item.find('date').text, '%Y-%m-%dT%H:%M:%SZ') < datetime.datetime.strptime(single_ticket_xml.find('displayDueDate').text, '%Y-%m-%dT%H:%M:%SZ'):
# 							print 'On Time based on last resolution',item.find('date').text,item.find('mobileNoteText').text
							self.byTech[tech][0] = self.byTech[tech][0] + 1
							self.byLocation[location][0] = self.byLocation[location][0] + 1
							self.byDate[date][0] = self.byDate[date][0] + 1
							status = 1
							break
						break


					if status == 0:
# 						print "Not closed on time and no comments"
						self.byTech[tech][1] = self.byTech[tech][1] + 1
						self.byLocation[location][1] = self.byLocation[location][1] + 1
						self.byDate[date][1] = self.byDate[date][1] + 1
						status = 1

				else:
						self.nonTechTickets = 1 + self.nonTechTickets
						status = 2

	def summarize_report(self):
		on_time_summary = 0
		past_due_summary = 0
		for t,v in self.byTech.iteritems():
# 			print "Tech: %s" % t
# 			print "OnTime: %s" % v[0]
# 			print "PastDue: %s" % v[1]
			on_time_summary = on_time_summary + v[0]
			past_due_summary = past_due_summary + v[1]
		return on_time_summary,past_due_summary


class Pie_Charts:

	whd_pies = []
	jss_pies = []

	def __init__(self):
		print "Making Pies"

	def data_to_pie_to_div(self,name,v,labels,title):
		pie_data = {
			'data': [{'labels': labels,
					  'values': [v[0],v[1]],
					  'name': name,
					  'marker': {'colors': ['rgb(86,169,246)', 'rgb(251,73,30)'],'line': {'width': '2', 'color': '#FFF'} },
					  'type': 'pie',
					  'hoverinfo':'label+percent+name+value',
					  'textinfo':'percentage'}],
			'layout': {'title': title % name}
			}

		if 'Checking' in title:
			pie_data['layout']['annotations'] = [
            {
                "font": {
                    "size": 14
                },
                "showarrow": False,
                "text": "%s of %s Total Devices Not Checking In" % (v[1], v[0] + v[1]),
                "x": .7,
                "y": -.2
            }]

		if 'Checking' in title:
			self.jss_pies.append(offline.plot(pie_data,output_type='div',include_plotlyjs=False,show_link=False))
		else:
			self.whd_pies.append(offline.plot(pie_data,output_type='div',include_plotlyjs=False,show_link=False))


def rotate_files():
	folder = HTML_FILENAME.rsplit('/',1)[0]
	yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
	try:
		os.rename(HTML_FILENAME, folder + '/%s.html' % yesterday.strftime("%Y-%m-%d"))
	except:
		print "Unable to move file"


def build_html(monthlyKPIBarChart):
	'''Write Head, all pies, and close to a file'''

	# Imports the javascript library
	lastrun = datetime.datetime.now().strftime('Last Run on %B %d, %Y')
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
	<body>
	'''
	# datetime.datetime.now().strftime('Last Run on %B %d, %Y')
	title_line = '''<h1>Technical Services Operations KPIs</h1>
		<h2>"Goals: CSAT: 95%, On-Time vs Past-Due: %75, 14 Day Check-in: 85%, 31 Day Check-in: 99%"</h2>
        <h4>{}</h4>'''.format(lastrun)

	div_wrapper_a = '''<div id='wrapper' class='pietime'>'''
	div_wrapper_b = '''</div>'''

	html_close = '''
	</body>
	</html>'''

	hr_html = '''<hr>'''

	hr = 1
	with open(HTML_FILENAME, 'w') as f:
		f.write(html_head)
		f.write(title_line)
		f.write(monthlyKPIBarChart)
		for pie in pie_charts.jss_pies:

			f.write(div_wrapper_a)
			f.write(pie)
			f.write(div_wrapper_b)

			if hr == 4:
				f.write(hr_html)
				hr = 0
			hr = hr + 1
		for pie in pie_charts.whd_pies:

			f.write(div_wrapper_a)
			f.write(pie)
			f.write(div_wrapper_b)

			if hr == 4:
				f.write(hr_html)
				hr = 0
			hr = hr + 1

		f.write(html_close)
		f.close()


def create_montly_bar_chart():
	"""Create the montly bar chart from the traces we built"""
	layout = dict(title = 'Service Operations Monthly KPIs',
              xaxis = dict(title = 'Month'),
              yaxis = dict(title = 'Percentage')
              )
#
# 	layout['annotations'] = [
#             {
#                 "font": {
#                     "size": 10
#                 },
#                 "showarrow": False,
#                 "text": "Goals: CSAT: 95%, On-Time vs Past-Due: %75, 14 Day Check-in: 85%, 31 Day Check-in: 99%",
#                 "x": 3,
#                 "y": 100
#             }]

	figure = dict(data=traces, layout=layout)
	monthly_kpi_bar_chart = offline.plot(figure,output_type='div',include_plotlyjs=False,show_link=False)
	return monthly_kpi_bar_chart


def jss_create_report():
	jss_report = JSSDeviceReport()
	labels = ['Checking in','Not checking in']

	# Create the all building pies
	pie_charts.data_to_pie_to_div("All Buildings Combined",jss_report.all_buildings_report[0:2],labels,'%s - 14 Day Computers Checking in')
	pie_charts.data_to_pie_to_div("All Buildings Combined",jss_report.all_buildings_report[2:4],labels,'%s - 31 Day Computers Checking in')
	pie_charts.data_to_pie_to_div("All Buildings Combined",jss_report.all_buildings_report[4:6],labels,'%s - 14 Day Mobile Devices Checking in')
	pie_charts.data_to_pie_to_div("All Buildings Combined",jss_report.all_buildings_report[6:8],labels,'%s - 31 Day Mobile Devices Checking in')


	# Create the individual building pies
	i = 0
	for i in range(len(jss_report.sorted_building_report)):
		pie_charts.data_to_pie_to_div(jss_report.sorted_building_report[i][0],jss_report.sorted_building_report[i][1][0:2],labels,'%s - 14 Day Computers Checking in')
		pie_charts.data_to_pie_to_div(jss_report.sorted_building_report[i][0],jss_report.sorted_building_report[i][1][2:4],labels,'%s - 31 Day Computers Checking in')
		pie_charts.data_to_pie_to_div(jss_report.sorted_building_report[i][0],jss_report.sorted_building_report[i][1][4:6],labels,'%s - 14 Day Mobile Devices Checking in')
		pie_charts.data_to_pie_to_div(jss_report.sorted_building_report[i][0],jss_report.sorted_building_report[i][1][6:8],labels,'%s - 31 Day Mobile Devices Checking in')

		i += 1


	#Monthly All Buildings Device reports for bar chart
	monthlyc14 = 100 * (float(jss_report.all_buildings_report[0]) / (float(jss_report.all_buildings_report[0] + jss_report.all_buildings_report[1])))
	monthlyc31 = 100 * (float(jss_report.all_buildings_report[2]) / (float(jss_report.all_buildings_report[2] + jss_report.all_buildings_report[3])))
	monthlym14 = 100 * (float(jss_report.all_buildings_report[4]) / (float(jss_report.all_buildings_report[4] + jss_report.all_buildings_report[5])))
	monthlym31 = 100 * (float(jss_report.all_buildings_report[6]) / (float(jss_report.all_buildings_report[6] + jss_report.all_buildings_report[7])))

	# Read in values from previous months
	import os.path
	SITE_ROOT = os.path.dirname(os.path.realpath(__file__))
	with open('%s/%s' % (SITE_ROOT, 'monthlydevice-test.txt'), 'r') as f:
		contents = f.readlines()

	all = []
	for i in contents:
		all.append(i.split(','))

	# Strip off the currently cached month
	lastmonth = 0
	if contents[0].split(',')[-1].strip() == months[-1]:
		lastmonth = 1

	c14 = []
	for i in range(len(all[1])-lastmonth):
		print i
		c14.append(all[1][i].strip())
	c14.append(monthlyc14)

	c31 = []
	for i in range(len(all[2])-lastmonth):
		c31.append(all[2][i].strip())
	c31.append(monthlyc31)

	m14 = []
	for i in range(len(all[3])-lastmonth):
		m14.append(all[3][i].strip())
	m14.append(monthlym14)

	m31 = []
	for i in range(len(all[4])-lastmonth):
		m31.append(all[4][i].strip())
	m31.append(monthlym31)

	if contents[0].split(',')[-1].strip() != months[-1]:
	# Write new values back
	# Need to decide if we will do it or not (write on last date?)
		contents[0] = contents[0].strip() + ',' + months[-1] + '\n'
		contents[1] = contents[1].strip() + ',' + str(monthlyc14) + '\n'
		contents[2] = contents[2].strip() + ',' + str(monthlyc31) + '\n'
		contents[3] = contents[3].strip() + ',' + str(monthlym14) + '\n'
		contents[4] = contents[4].strip() + ',' + str(monthlym31) + '\n'

		with open('%s/%s' % (SITE_ROOT,'monthlydevice-test.txt'), 'w') as f:
			f.writelines(contents)


	trace = go.Scatter(
		y = c14,
		x = months,
		name = 'Computer 14 Day Check in'
	)

	traces.append(trace)

	trace = go.Scatter(
		y = c31,
		x = months,
		name = 'Computer 31 Day Check in'
	)
	traces.append(trace)

	trace = go.Scatter(
		y = m14,
		x = months,
		name = 'Mobile Device 14 Day Check in'
	)
	traces.append(trace)

	trace = go.Scatter(
		y = m31,
		x = months,
		name = 'Mobile Device 31 Day Check in'
	)

	traces.append(trace)


def whd_create_survey_report():
	whd_survey_report = WHDSurveyReport()

	# Cstat pie
	# Value returned is the inverse of the actual value since the id is worth the weight in reverse order (easier than translating the string value)
	values = [5 - whd_survey_report.csat, whd_survey_report.csat]
	labels = ['Yes','No']
	pie_charts.data_to_pie_to_div("CSAT Score",values,labels,'%s - All Technology Tickets')

	# Setup the closure question pie
	print whd_survey_report.survey_time_to_close
	print type(whd_survey_report.survey_time_to_close)
	values = [whd_survey_report.survey_time_to_close, 1 - whd_survey_report.survey_time_to_close]
	labels = ['Satisfied','Not Satisfied']
	pie_charts.data_to_pie_to_div("Was your issue handled in a timely manner?",values,labels,'%s - All Technology Tickets')

	# csat bar
	monthly_cstat_y_values = []
	for i in range(len(whd_survey_report.monthly_csat)):
		months.append("%s-%s" % (whd_survey_report.monthly_csat[i][2],whd_survey_report.monthly_csat[i][1]))
		monthly_cstat_y_values.append(100 * ((5 - float(whd_survey_report.monthly_csat[i][0]))/5))

	trace = go.Scatter(
		y = monthly_cstat_y_values,
		x = months,
		name = 'CSAT Score'
	)

	traces.append(trace)

	monthly_ttc_y_values = []
	for i in range(len(whd_survey_report.monthly_time_to_close)):
		monthly_ttc_y_values.append(100 * float(whd_survey_report.monthly_time_to_close[i][0]))

	trace = go.Scatter(
		y = monthly_ttc_y_values,
		x = months,
		name = 'Closed on Time Survey'
	)

	traces.append(trace)


def whd_create_ot_vs_pd():
	# Get the ticket date for past due vs on time (not using byloc yet)

	whd_ot_vs_pd_report = WHDOTvsPDReport()

	# Setup the pie for past due vs on time
	values = [whd_ot_vs_pd_report.on_time_summary, whd_ot_vs_pd_report.past_due_summary]
	labels = ['Resolved On Time','Resoved Past Due']
	pie_charts.data_to_pie_to_div("Past Due vs On Time",values,labels,'%s - All Technology Tickets')

	# Go over byDate info on tickets
	monthly_ot_vs_pd_values_unsorted = []
	for k,v in whd_ot_vs_pd_report.byDate.iteritems():
		monthly_ot_vs_pd_values_unsorted.append([k,100 * (float(v[0]) / (float(v[0]) + float(v[1])))])

	# Sort by Date (11-2016)
	monthly_ot_vs_pd_values_sorted = sorted(monthly_ot_vs_pd_values_unsorted, key=lambda x: datetime.datetime.strptime(x[0], '%m-%Y'))


	for i in range(len(monthly_ot_vs_pd_values_sorted)):
		monthly_ot_vs_pd_values_sorted[i][1]

	monthly_ot_vs_pd_y_values = []
	for i in range(len(monthly_ot_vs_pd_values_sorted)):
		monthly_ot_vs_pd_y_values.append(monthly_ot_vs_pd_values_sorted[i][1])


	trace = go.Scatter(
		y = monthly_ot_vs_pd_y_values,
		x = months,
		name = 'On-Time vs Past-Due'
	)

	traces.append(trace)


def main():
	# Rotate lastest html file and rename to yesterday's date
	rotate_files()

	# Web Help Desk Survey - Create the pies and get monthly information
	whd_create_survey_report()

	# Web Help Desk On-Time vs Past-Due - Create the pies and get monthly information
	whd_create_ot_vs_pd()

	# JSS Report - this comes after because we get months from the whd reports
	jss_create_report()

	# Create Monthly Bar Chart
	monthly_kpi_bar_chart = create_montly_bar_chart()

	# Build HTML from pies and bar chart objects
	build_html(monthly_kpi_bar_chart)



if __name__ == '__main__':
	logging.info('Making charts!')
	# Start up the Pies
	pie_charts = Pie_Charts()

	# Start up the traces
	traces = []

	# Start up the months
	months = []

	main()
	logging.info('Done making charts!')
	sys.exit(0)
