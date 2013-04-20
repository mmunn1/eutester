# Software License Agreement (BSD License)
#
# Copyright (c) 2009-2011, Eucalyptus Systems, Inc.
# All rights reserved.
#
# Redistribution and use of this software in source and binary forms, with or
# without modification, are permitted provided that the following conditions
# are met:
#
#   Redistributions of source code must retain the above
#   copyright notice, this list of conditions and the
#   following disclaimer.
#
#   Redistributions in binary form must reproduce the above
#   copyright notice, this list of conditions and the
#   following disclaimer in the documentation and/or other
#   materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Author: vic.iglesias@eucalyptus.com
import re
import copy
import time
from boto.ec2.regioninfo import RegionInfo
import boto
from eutester import Eutester


CWRegionData = {
    'us-east-1': 'monitoring.us-east-1.amazonaws.com',
    'us-west-1': 'monitoring.us-west-1.amazonaws.com',
    'eu-west-1': 'monitoring.eu-west-1.amazonaws.com',
    'ap-northeast-1': 'monitoring.ap-northeast-1.amazonaws.com',
    'ap-southeast-1': 'monitoring.ap-southeast-1.amazonaws.com'}

DimensionArray      = ['AutoScalingGroupName', 'ImageId', 'InstanceId', 'InstanceType']

StatsArray          = ['Average', 'Sum', 'Maximum', 'Minimum','SampleCount']

InstanceMetricArray = [
                      ['CPUUtilization','Percent'],
                      ['DiskReadOps',   'Count'],
                      ['DiskWriteOps',  'Count'],
                      ['DiskReadBytes', 'Bytes'],
                      ['DiskWriteBytes','Bytes'],
                      ['NetworkIn',     'Bytes'],
                      ['NetworkOut',    'Bytes']
                      ]

StatusMetricArray   = [
                      ['StatusCheckFailed',         'Count'],
                      ['StatusCheckFailed_Instance','Count'],
                      ['StatusCheckFailed_System',  'Count']
                      ]
EbsMetricsArray     = [
                      ['VolumeReadBytes','Bytes'],
                      ['VolumeWriteBytes','Bytes'],
                      ['VolumeReadOps','Count'],
                      ['VolumeWriteOps','Count'],
                      ['VolumeTotalReadTime','Seconds'],
                      ['VolumeTotalWriteTime','Seconds'],
                      ['VolumeIdleTime','Seconds'],
                      ['VolumeQueueLength','Count'],
                      ['VolumeThroughputPercentage','Percent'],
                      ['VolumeConsumedReadWriteOps','Count']
                      ]

class CWops(Eutester):
    @Eutester.printinfo
    def __init__(self, host=None, credpath=None, endpoint=None, aws_access_key_id=None, aws_secret_access_key=None,
                 username="root", region=None, is_secure=False, path='/', port=80, boto_debug=0):
        """

        :param host:
        :param credpath:
        :param endpoint:
        :param aws_access_key_id:
        :param aws_secret_access_key:
        :param username:
        :param region:
        :param is_secure:
        :param path:
        :param port:
        :param boto_debug:
        """
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.account_id = None
        self.user_id = None
        super(CWops, self).__init__(credpath=credpath)

        self.setup_cw_connection(host=host,
                                 region=region,
                                 endpoint=endpoint,
                                 aws_access_key_id=self.aws_access_key_id,
                                 aws_secret_access_key=self.aws_secret_access_key,
                                 is_secure=is_secure,
                                 path=path,
                                 port=port,
                                 boto_debug=boto_debug)
        self.poll_count = 48
        self.username = username
        self.test_resources = {}
        self.setup_cw_resource_trackers()

    @Eutester.printinfo
    def setup_cw_connection(self, endpoint=None, aws_access_key_id=None, aws_secret_access_key=None, is_secure=True,
                            host=None,
                            region=None, path="/", port=443, boto_debug=0):
        """

        :param endpoint:
        :param aws_access_key_id:
        :param aws_secret_access_key:
        :param is_secure:
        :param host:
        :param region:
        :param path:
        :param port:
        :param boto_debug:
        :raise:
        """
        cw_region = RegionInfo()
        if region:
            self.debug("Check region: " + str(region))
            try:
                if not endpoint:
                    cw_region.endpoint = CWRegionData[region]
                else:
                    cw_region.endpoint = endpoint
            except KeyError:
                raise Exception('Unknown region: %s' % region)
        else:
            cw_region.name = 'eucalyptus'
            if not host:
                if endpoint:
                    cw_region.endpoint = endpoint
                else:
                    cw_region.endpoint = self.get_cw_ip()
        connection_args = {'aws_access_key_id': aws_access_key_id,
                           'aws_secret_access_key': aws_secret_access_key,
                           'is_secure': is_secure,
                           'debug': boto_debug,
                           'port': port,
                           'path': path,
                           'region': cw_region}

        if re.search('2.6', boto.__version__):
            connection_args['validate_certs'] = False

        try:
            cw_connection_args = copy.copy(connection_args)
            cw_connection_args['path'] = path
            cw_connection_args['region'] = cw_region
            self.debug("Attempting to create cloud watch connection to " + cw_region.endpoint + str(port) + path)
            self.cw = boto.connect_cloudwatch(**cw_connection_args)
        except Exception, e:
            self.critical("Was unable to create Cloud Watch connection because of exception: " + str(e))

    def setup_cw_resource_trackers(self):
        """
        Setup keys in the test_resources hash in order to track artifacts created
        """
        self.test_resources["alarms"] = []
        self.test_resources["metric"] = []
        self.test_resources["datapoint"] = []

    def get_cw_ip(self):
        """Parse the eucarc for the AWS_CLOUDWATCH_URL"""
        cw_url = self.parse_eucarc("AWS_CLOUDWATCH_URL")
        return cw_url.split("/")[2].split(":")[0]

    def get_namespaces(self):
        """
        Convenience function for easily segregating metrics into their namespaces

        :return: Dict where key is the Namespace and the value is a list with all metrics
        """
        metrics= self.cw.list_metrics()
        namespaces = {}
        for metric in metrics:
            if not namespaces[metric.namespace]:
                namespaces[metric.namespace] = [metric]
            else:
                namespaces[metric.namespace].append(metric)
        return namespaces

    def list_metrics( self, next_token=None, dimensions=None, metric_name=None, namespace=None ):
        self.debug("Calling list_metrics( {p1}, {p2}, {p3}, {p4} )".format(p1=next_token, p2=dimensions, p3=metric_name, p4=namespace))
        return self.cw.list_metrics(next_token , dimensions, metric_name, namespace)

    def get_metric_statistics( self, period, start_time, end_time, metric_name, namespace, statistics, dimensions=None, unit=None):
        self.debug("Calling get_metric_statistics( {p1}, {p2}, {p3}, {p4}, {p5}, {p6}, {p7}, {p8} )".format(
                   p1=period, p2=start_time, p3=end_time, p4=metric_name, p5=namespace, p6=statistics, p7=dimensions, p8=unit))
        return self.cw.get_metric_statistics(period, start_time, end_time, metric_name, namespace, statistics, dimensions, unit)

    def put_metric_data( self, namespace, name, value=None, timestamp=None, unit=None, dimensions=None, statistics=None):
        self.debug("Calling put_metric_data( {p1}, {p2}, {p3}, {p4}, {p5}, {p6}, {p7} )".format(
                   p1=namespace, p2=name, p3=value, p4=timestamp, p5=unit, p6=dimensions, p7=dimensions))
        return self.cw.put_metric_data(namespace, name, value, timestamp, unit, dimensions, statistics)

    def wait_for_monitoring(self, total):
        while (total > 0):
            minutes=total/60
            seconds=total%60
            self.debug("Waiting for metrics to populate " + str(minutes) + " Minutes " + str(seconds) + " Seconds remaining.")
            time.sleep(10)
            total= total - 10

    def get_dimension_array(self):
        return DimensionArray

    def get_stats_array(self):
        return StatsArray

    def get_instance_metrics_array(self):
        return InstanceMetricArray

    def get_status_metric_array(self):
        return StatusMetricArray

    def get_ebs_metrin_array(self):
        return EbsMetricsArray
