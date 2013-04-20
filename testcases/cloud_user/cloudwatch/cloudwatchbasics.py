#!/usr/bin/python
import time
from eucaops import Eucaops
from eucaops import CWops
from eutester.eutestcase import EutesterTestCase
from boto.ec2.cloudwatch import Metric
import datetime

class newDimension(dict):
    def __init__(self, name, value):
        self[name] = value

class CloudWatchBasics(EutesterTestCase):
    def __init__(self, extra_args= None):
        self.setuptestcase()
        self.setup_parser()
        if extra_args:
            for arg in extra_args:
                self.parser.add_argument(arg)
        self.get_args()
        # Setup basic eutester object
        if self.args.region:
            self.tester = CWops( credpath=self.args.credpath, region=self.args.region)
        else:
            self.tester = Eucaops(config_file=self.args.config, password=self.args.password, credpath=self.args.credpath)
        self.start_time =  str(int(time.time()))
        self.namespace = "Namespace-" + self.start_time
        self.keypair = self.tester.add_keypair()
        self.group = self.tester.add_group()
        # How long to wait in seconds for monitoring to populate
        self.monitoring_wait_time=250
        # Number of instances you want to run
        self.runInstances(1)

    def clean_method(self):
        self.tester.cleanup_artifacts()
        self.tester.delete_keypair(self.keypair)
        self.tester.local("rm " + self.keypair.name + ".pem")
        pass

    def get_time_window(self, end=None, **kwargs):
        if not end:
            end = datetime.datetime.utcnow()
        start = end - datetime.timedelta(**kwargs)
        return (start,end)

    def print_timeseries_for_graphite(self, timeseries):
            for datapoint in timeseries:
                print "graph.Namespace-1361426618 " + str(int(datapoint['Average'])) + " " + \
                      str((datapoint['Timestamp'] - datetime.datetime(1970,1,1)).total_seconds())

    def runInstances(self, numMax):
        self.instanceids = []
        #Start instance with monitoring_enabled.
        self.image = self.tester.get_emi(root_device_type="instance-store")
        self.instance_type = "m1.medium"
        self.reservation = self.tester.run_instance(image=self.image,
                                                    keypair=self.keypair.name,
                                                    group=self.group,
                                                    type=self.instance_type,
                                                    min=1,
                                                    max=numMax,
                                                    is_reachable=False,
                                                    monitoring_enabled=True)
        # Make sure the instance is running.
        for instance in self.reservation.instances:
            if instance.state == "running":
                self.instanceids.append(str(instance.id))
        self.tester.wait_for_monitoring(self.monitoring_wait_time)

    def PutDataGetStats(self):
        seconds_to_put_data = 120
        metric_data = 1
        time_string =  str(int(time.time()))
        metric_name = "Metric-" + time_string
        incrementing = True
        while datetime.datetime.now().second != 0:
            self.tester.debug("Waiting for minute edge")
            self.tester.sleep(1)
        start = datetime.datetime.utcnow()
        for i in xrange(seconds_to_put_data):
            self.tester.put_metric_data(self.namespace, [metric_name],[metric_data])
            if metric_data == 600 or metric_data == 0:
                incrementing = not incrementing
            if incrementing:
                metric_data += 1
            else:
                metric_data -= 1
            self.tester.sleep(1)
        end = start + datetime.timedelta(minutes=2)
        metric = self.tester.list_metrics(namespace=self.namespace)[0]
        assert isinstance(metric,Metric)
        stats_array = metric.query(start_time=start, end_time=end, statistics=self.tester.get_stats_array())
        assert len(stats_array) == 2
        if stats_array[0]['Minimum'] == 1:
            first_sample = stats_array[0]
            second_sample = stats_array[1]
        else:
            second_sample = stats_array[0]
            first_sample = stats_array[1]
        print stats_array

        ##Check sample 1
        assert first_sample['Maximum'] < 60 and first_sample['Minimum'] > 0
        assert first_sample['Average'] < 34 and first_sample['Average'] > 26
        assert first_sample['Sum'] < 1800 and first_sample['Sum'] > 1500
        assert first_sample['SampleCount'] > 50
        ##Check sample 2
        assert second_sample['Maximum'] < 120 and second_sample['Minimum'] > 50
        assert second_sample['Average'] < 90 and second_sample['Average'] > 80
        assert second_sample['Sum'] < 6000 and second_sample['Sum'] > 4600
        assert second_sample['SampleCount'] > 50

        assert first_sample['Average'] < second_sample['Average']
        assert first_sample['Sum'] < second_sample['Sum']
        assert first_sample['Maximum'] < second_sample['Maximum']
        assert first_sample['Minimum'] < second_sample['Minimum']

    def ListMetricsTest(self):
        self.debug("Get Metric list")
        outList = self.tester.list_metrics()
        self.debug("Checking to see if list is populated at all.")
        assert len(outList) > 0
        expectedMetricList = self.tester.get_instance_metrics_array()
        self.debug("Checking to see if we get all the expected instance metrics.")
        for metric in expectedMetricList :
            assert str(outList).count(metric[0]) > 0
            self.debug("Metric " + metric[0])
        self.debug("Make sure all Instance dimensions are listed.")
        found=False
        for instance in self.instanceids:
            for metric in outList:
                if str(metric.dimensions).count(instance) :
                    self.debug("Dimension " + str(metric.dimensions))
                    found=True
                    break
            assert found
            found=False

        self.debug("Check list_metrics filtering parameters")
        outList = self.tester.list_metrics(namespace="AWS/EC2")
        assert len(outList) > 0
        outList = self.tester.list_metrics(namespace="NonExistent-NameSpace")
        assert len(outList) == 0
        outList = self.tester.list_metrics(metric_name=expectedMetricList[0][0])
        assert len(outList) > 0
        outList = self.tester.list_metrics(metric_name="NonExistent-Metric-Name")
        assert len(outList) == 0
        outList = self.tester.list_metrics(dimensions=newDimension("InstanceId", self.instanceids[0]))
        assert len(outList) > 0
        outList = self.tester.list_metrics(dimensions=newDimension("InstanceId","NonExistent-InstanceId"))
        assert len(outList) == 0
        outList = self.tester.list_metrics(dimensions=newDimension("ImageId", self.image.id))
        assert len(outList) > 0
        outList = self.tester.list_metrics(dimensions=newDimension("ImageId","NonExistent-imageId"))
        assert len(outList) == 0
        outList = self.tester.list_metrics(dimensions=newDimension("InstanceType", self.instance_type))
        assert len(outList) > 0
        outList = self.tester.list_metrics(dimensions=newDimension("InstanceType","NonExistent-InstanceType"))
        assert len(outList) == 0
        """
        TODO:
        outList = self.tester.list_metrics(dimensions=newDimension("AutoScalingGroupName", "VALID_GROUP_NAME"))
        assert len(outList) > 0
        """
        outList = self.tester.list_metrics(dimensions=newDimension("AutoScalingGroupName","NonExistent-AutoScalingGroupName"))
        assert len(outList) == 0

    def GetInstanceMetricStatsTest(self):
        # get_metric_statistics parameters
        period       = 60
        end          = datetime.datetime.utcnow()
        start        = end - datetime.timedelta(minutes=5)
        stats        = self.tester.get_stats_array()
        metricNames  = self.tester.get_instance_metrics_array() # metricNames[i][0] gives you the metric name
        namespace    = 'AWS/EC2'
        dimension    = newDimension("InstanceId", str(self.instanceids[0]))
        unit         = metricNames  # metricNames[i][1] gives you the associated metric Unit

        #Check to make sure we are getting all metrics and statistics
        for i in range(len(metricNames)):
            for j in range(len(stats)):
                metricName = metricNames[i][0]
                statisticName = stats[j]
                unitType =  unit[i][1]
                metrics = self.tester.get_metric_statistics(period, start, end, metricName, namespace, statisticName, dimensions=dimension, unit=unitType)
                # This assures we are getting all statistics for all Instance metrics.
                assert int(len(metrics)) > 0
                statisticValue = str(metrics[0][statisticName])
                self.debug(metricName + " : " + statisticName + "=" + statisticValue + " " + unitType)

    def VerifyMetricStatValues(self):
        """
        TODO: Verify we are getting correct Metric statistic values ????
        """
        pass

    def GetEbsMetricStats(self):
        """
        TODO: Will these be in 3.0??
        """
        pass

    def PutMetricAlarm(self):
        pass

    def SetAlarmState(self):
        pass

    def DeleteAlarms(self):
        pass

    def DescribeAlarms(self):
        pass

    def DescribeAlarmsForMetric(self):
        pass

    def DescribeAlarmHistory(self):
        pass

if __name__ == "__main__":
    testcase = CloudWatchBasics()
    ### Use the list of tests passed from config/command line to determine what subset of tests to run
    ### or use a predefined list  "VolumeTagging", "InstanceTagging", "SnapshotTagging", "ImageTagging"
    list = testcase.args.tests or ["PutDataGetStats","ListMetricsTest","GetInstanceMetricStatsTest"]

    ### Convert test suite methods to EutesterUnitTest objects
    unit_list = [ ]
    for test in list:
        unit_list.append( testcase.create_testunit_by_name(test) )

    ### Run the EutesterUnitTest objects
    result = testcase.run_test_case_list(unit_list,clean_on_exit=True)
    exit(result)