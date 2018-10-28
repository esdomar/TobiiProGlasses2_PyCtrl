import threading
import pylsl
import numpy as np
import urllib2
import json

class TimeSynchronization():
	def __init__(self, data_socket, base_url):
		#Clock sync parameters  
		self.time_sync_local_buffer = []
		self.sync_local_roundtrip = []  
		self.sync_ru_buffer = [] 
		self.sync_status = False  
		self.sync_age = 0.1/9 #Y(new offset) = 0.001667*x(time) + Original offset
		self.time_to_sync = 0.2 #Start by synching every 200ms
		self.streaming_start_time = 0 #Start by synching every 200ms 
		self.last_ts = 0  
		self.regression = True  
		self.last_roundtrip = 0
		self.n_update_sample = 0
		self.regression_check = 0
		self.first_time_sync = False
		self.just_updated = False
		self.streaming = False
		self.data_socket = data_socket
		self.base_url = base_url
		self.reg_coef = [0,0]
		self.reg_coef_temp = [0,0]

	def start_synchronization(self):
		self.tsync = threading.Timer(10, self.send_synchronization_event, [self.data_socket])
		self.tsync.start() 
		self.streaming = True
		self.streaming_start_time = pylsl.local_clock()

	def ts_to_local(self, ts, check_sync=False):
		m = self.reg_coef[0]
		c = self.reg_coef[1]
		ts_local = float(m * int(ts) + c)
		if check_sync:
			ts_local = self.check_sync_timing(ts, ts_local)
		return ts_local
		
	def check_sync_timing(self, ts, ts_local):
		if ts_local - self.last_ts  < 0.008 and self.just_updated:
		  	ts_local = self.last_ts + 0.008
		elif ts_local - self.last_ts  > 0.012 and self.first_time_sync and self.just_updated:
		  	ts_local = self.last_ts + 0.012
		else:
			self.just_updated = False
		self.last_ts = ts_local
		if not self.first_time_sync:
			self.first_time_sync = True
		return ts_local
	
	def send_synchronization_event(self, socket):
		time_before = pylsl.local_clock()
		self.send_event('Sync_Event', int(time_before))
		time_after = pylsl.local_clock()
		roundtrip = (time_after - time_before)/float(2)
		self.sync_local_buffer.append(time_before + roundtrip)
		self.sync_local_roundtrip.append(roundtrip)
		self.set_time_to_sync()

		if self.streaming:   
			self.tsync.cancel()
			self.tsync = threading.Timer(self.time_to_sync, self.send_synchronization_event, [self.data_socket])
			self.tsync.start()

	def set_time_to_sync(self):		
		if not self.sync:  
			self.last_roundtrip = self.sync_local_buffer[-1]  
			self.time_to_sync = 0.3 
		if not self.regression:
			self.time_to_sync = 0.8
		elif pylsl.local_clock() - self.streaming_start_time > 80 :
			self.time_to_sync = 5 
		elif pylsl.local_clock() - self.streaming_start_time > 3:
			self.time_to_sync = 1

	def update_sync(self, ts):
		self.sync_ru_buffer.append(int(ts))      
		n = min([len(self.sync_local_buffer), len(self.sync_ru_buffer)])
		self.last_roundtrip += self.last_roundtrip * self.sync_age
		if n > 6 and (self.last_roundtrip > self.sync_local_roundtrip[n-1] or self.sync_local_roundtrip[n-1] < 0.005): 	#If enough data points and low roundtrip latency		
			local_array = np.array(self.sync_local_buffer[:n])
			ru_array = np.array(self.sync_ru_buffer[:n])
			X = np.vstack([ru_array, np.ones(len(ru_array))]).T
			self.reg_coef_temp[0],  self.reg_coef_temp[1] = np.linalg.lstsq(X, local_array, rcond=None)[0]
			if self.sync:
				is_regression_valid = self.check_regression(ts)
				if is_regression_valid:
					self.update_regression(n, X, local_array)
				else:
					self.dont_update_regression(n, False, "DErrorRegressionNOTUpdated ")
			else:
				self.reg_coef = self.reg_coef_temp[:]
				self.regression = True   
			if not self.sync:
				self.sync_status = True
				print "starting streaming now"
		else: #Not enough data points or high latency
			if self.sync: #Not enough data points
				self.dont_update_regression(n, True, 'DRoundTripError')
			else: #Not enough points
				if len(self.sync_local_roundtrip) > 2:
					if not self.last_roundtrip > self.sync_local_roundtrip[n-1]: 
						self.dont_update_regression(n, True, "DRoundTripError ")				
      
	def update_regression(self, n, X, local_array):
		self.n_update_sample += 1
		if self.n_update_sample == 3:
			self.reg_coef = self.reg_coef_temp[:]

			self.regression = True
			self.last_roundtrip = self.sync_local_roundtrip[n-1]
			self.n_update_sample = 0	
			self.just_updated = True

	def dont_update_regression(self, n, regression, message):
		self.regression = regression 
		del self.sync_ru_buffer[n-1]  
		del self.sync_local_buffer[n-1]
		del self.sync_local_roundtrip[n-1]

	def check_regression(self, ts):
		m_temp = self.reg_coef_temp[0]
		c_temp = self.reg_coef_temp[1]
		m = self.reg_coef[0]
		c = self.reg_coef[1]
		local_new =  m_temp* int(ts) + c_temp
		local_old = m* int(ts) + c 
		self.regression_check +=1
		if abs(local_new - local_old) < 0.02 or self.regression_check == 2:
			self.regression_check = 1
		 	return True
		else:
			return False

	def look_for_sync_event(self, jsondata):
		ts = str(jsondata['ts'])
		if 'ets' in jsondata.keys():
			if jsondata['type'] == 'Sync_Event':
				self.update_sync(ts)
		return self.sync
				

	def stop_sync(self):
		self.sync_local_buffer = []
		self.sync_local_roundtrip = []  
		self.sync_ru_buffer = [] 
		self.sync_status = False  
		self.sync_age = 0.1/9 #Y(new offset) = 0.001667*x(time) + Original offset
		self.reg_coef = [0,0]
		self.reg_coef_temp = [0,0]
		self.time_to_sync = 0.2 #Start by synching every 200ms
		self.streaming_start_time = 0 #Start by synching every 200ms 
		self.last_ts = 0  
		self.regression = True  
		self.last_roundtrip = 0
		self.n_update_sample = 0
		self.regression_check = 0
		self.first_time_sync = False
		self.just_updated = False
		self.streaming = False

	def send_event(self, event_type, ets = '',  event_tag = ''):
		data = {'ets': ets, 'type': event_type, 'tag': event_tag}
		self.post_request('/api/events', data)    

	def post_request(self, api_action, data=None):
		url = self.base_url + api_action
		req = urllib2.Request(url)
		req.add_header('Content-Type', 'application/json')
		data = json.dumps(data)
		urllib2.urlopen(req, data)

