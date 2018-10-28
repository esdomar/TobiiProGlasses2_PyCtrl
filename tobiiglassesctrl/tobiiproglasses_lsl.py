# tobiiglassescontroller.py: A Python controller for Tobii Pro Glasses 2
#
# Copyright (C) 2018  Estefania Dominguez
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>


import time
import threading
import socket
import pylsl

from tobiiglassesctrl import TobiiGlassesController
          
class TobiiGlassesController_lsl():
    def __init__(self, ip = "192.168.71.50"): #Wireless connection by default
        self.lsl_on = False
        self.sr = None
        self.streams = []
        self.gaze_outlet = None
        self.triggers_outlet = None
        self.video_sync_outlet = None
        self.data_streams = []
        try:
            print 'Connecting to Glasses 2. ip:', ip             
            self.tobiiglasses = TobiiGlassesController(ip)
            self.sr = self.tobiiglasses.get_configuration()['sr']
            self.lsl_status = True
            print 'Connected to Tobii Glasses at:', self.sr, 'Hz'
        except:
            self.lsl_status = False
            print 'Connection to Tobii Glasses 2 failed. Check network connection and try again'
    
    def initialize_lsl(self,  stream):
        if stream == 'gaze' and stream not in self.streams:
            self.tobiiglasses.start_streaming(False)
            time.sleep(2)
            raw_data_streams = self.tobiiglasses.get_data()
            self.tobiiglasses.stop_streaming()
            gaze_data_streams =  self.split_datastreams(raw_data_streams[stream]) 
            self.gaze_info = pylsl.stream_info("TobiiGlasses2", "Gaze", len(gaze_data_streams), self.sr, pylsl.cf_double64, "Tobii-" + socket.gethostname());
            self.gaze_channels = self.gaze_info.desc().append_child("channels")
            self.gaze_channels = self.append_channels(gaze_data_streams, self.gaze_channels)            
            self.gaze_outlet = pylsl.stream_outlet(self.gaze_info)
            self.streams.append(stream)
        
        elif stream == 'triggers'and stream not in self.streams:
            trigger_data_streams = [ 'dir']                
            self.triggers_info = pylsl.stream_info("TobiiTriggers", 'Markers',len(trigger_data_streams),0,'string',"Tobii-" + socket.gethostname())
            self.trigger_channels = self.triggers_info.desc().append_child("channels")
            self.trigger_channels = self.append_channels(trigger_data_streams, self.trigger_channels)
            
            self.triggers_outlet = pylsl.stream_outlet(self.triggers_info)
            self.streams.append(stream)
        elif stream == 'video_sync'and stream not in self.streams:
            video_sync_streams = [ 'video_sync_ts_local', 'vts']                
            self.video_sync_info = pylsl.stream_info("TobiiVideoSync", 'Markers',len(video_sync_streams),0,'string',"Tobii-" + socket.gethostname())
            self.video_sync_channels = self.video_sync_info.desc().append_child("channels")
            self.video_Sync_channels = self.append_channels(video_sync_streams, self.video_sync_channels)
            
            self.video_sync_outlet = pylsl.stream_outlet(self.video_sync_info)
            self.streams.append(stream)

        else:
            print 'Data stream already initialized', stream

        return self.lsl_on

    def append_channels(self, data, info_channels ):
            for c in data:
                info_channels.append_child("channel") \
                .append_child_value("label", c) \
                .append_child_value("type", "Triggers")
                self.data_streams.append(c)
            return info_channels
    
    def split_datastreams(self, data):
        data_keys = data.keys()        
        datastream = data[data_keys[0]]
        plain_datastreams = []
        for key in datastream.keys(): 
            if type(datastream[key]) != list:  
                plain_datastreams.append(key)
            elif len(datastream[key]) > 2:
                plain_datastreams.append(key + '.x')
                plain_datastreams.append(key + '.y')
                plain_datastreams.append(key + '.z')
            else:
                plain_datastreams.append(key + '.x')
                plain_datastreams.append(key + '.y')   
        return plain_datastreams
    				     
    def get_connection_status(self):
        return self.lsl_status
    
    def start_streaming(self):
        self.lsl_on = True
        self.tobiiglasses.start_streaming()
        self.tl = threading.Timer(0, self.get_data)
        self.tl.start()
    
    def stop_streaming(self):
        self.lsl_on = False
        self.tl.join()
        self.disconnect_lsl()
        self.tobiiglasses.stop_streaming()
        
    def start_recording(self, recording_id):
        self.tobiiglasses.start_recording(recording_id)
        print self.streams
        
    def stop_recording(self, recording_id):
        self.tobiiglasses.stop_recording(recording_id)
        
    def disconnect_lsl(self):
        if self.lsl_on:
            self.stop_streaming()
        if self.gaze_outlet:
            del self.gaze_outlet
            self.gaze_info = None
            self.gaze_channels = None
            self.gaze_outlet = None
        if self.triggers_outlet:
            del self.triggers_outlet
            self.triggers_info = None
            self.triggers_channels = None 
            self.triggers_outlet = None
        if self.video_sync_outlet:
            del self.video_sync_outlet
            self.video_sync_info = None
            self.video_sync_channels = None 
            self.video_sync_outlet = None
        self.data_streams = []
        self.streams = []
        return self.lsl_on
								
    def get_data(self):
        while self.lsl_on:
            time.sleep(0.5)
            data = self.tobiiglasses.get_data()
            for key in self.streams:
                if not data[key] == {}:
                    timestamps = data[key].keys()
                    timestamps.sort()
                    for ts in timestamps:
                        self.push_sample(data[key][ts], key)
                                  
    def push_sample (self, sample, key):
        try:	
            data = []
            for datastream in self.data_streams: 
                datastream_split = datastream.split('.')
                for s in sample:
                    if s == datastream_split[0]:
                        try:       
                            if datastream_split[1] == 'x': 
                                data.append(sample[s][0])
                            elif datastream_split[1] == 'y':
                                data.append(sample[s][1])
                            else:
                                data.append(sample[s][2])
                        except:
                            data.append(sample[s])
            if key == 'gaze':
                collection_time = sample['ts_local_sync']
                self.gaze_outlet.push_sample(pylsl.vectord(data), collection_time, True)
            elif key == 'triggers':
                collection_time = sample['trigger_ts_local_sync']
                self.triggers_outlet.push_sample(pylsl.vectord(data), collection_time, True)
            elif key == 'video_sync':
                collection_time = sample['video_sync_ts_local_sync']
                self.video_sync_outlet.push_sample(pylsl.vectord(data), collection_time, True)            
        except:
            print'Error when pushing sample'															        