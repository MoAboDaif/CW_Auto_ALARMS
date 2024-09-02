import boto3
import json

def lambda_handler(event, context):
    # Initialize EC2 and CloudWatch clients
    ec2 = boto3.client('ec2')
    cloudwatch = boto3.client('cloudwatch')
    
    # Extract instance ID from event
    instance_id = event['detail']['instance-id']
    
    try:
        # Retrieve instance details
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance_info = response['Reservations'][0]['Instances'][0]
        tags = instance_info.get('Tags', [])
        instance_name = next((tag['Value'] for tag in tags if tag['Key'] == 'Name'), 'UnnamedInstance')
        image_id = instance_info.get('ImageId', 'UnknownImageId')
        instance_type = instance_info.get('InstanceType', 'UnknownInstanceType')

        # Check if any tag value contains 'first_run'
        should_create_alarm = any('first_run' in tag['Value'] for tag in tags if tag['Key'] == 'ALARM')
        
        if not should_create_alarm:
            # If the condition is not met, exit the function
            return {
                'statusCode': 200,
                'body': json.dumps('Instance does not meet the tag criteria. No alarm created.')
            }
        
        # Define the alarms' parameters for CPU, Memory, and Disk usage
        alarms = [
            {
                'name': f'{instance_name}-{instance_id}-CPUUtilization',
                'metric_name': 'CPUUtilization',
                'namespace': 'AWS/EC2',
                'dimensions': [{'Name': 'InstanceId', 'Value': instance_id}]
            },
            {
                'name': f'{instance_name}-{instance_id}-MemoryUtilization',
                'metric_name': 'mem_used_percent',
                'namespace': 'CWAgent',
                'dimensions': [
                    {'Name': 'InstanceId', 'Value': instance_id},
                    {'Name': 'ImageId', 'Value': image_id},
                    {'Name': 'InstanceType', 'Value': instance_type}
                ]
            },
            {
                'name': f'{instance_name}-{instance_id}-DiskUtilization',
                'metric_name': 'disk_used_percent',
                'namespace': 'CWAgent',
                'dimensions': [
                    {'Name': 'InstanceId', 'Value': instance_id},
                    {'Name': 'ImageId', 'Value': image_id},
                    {'Name': 'InstanceType', 'Value': instance_type},
                    {'Name': 'path', 'Value': '/'},  # Assuming root filesystem
                    {'Name': 'device', 'Value': 'xvda1'},  # Adjust based on your setup
                    {'Name': 'fstype', 'Value': 'xfs'}  # Adjust based on your setup
                ]
            }
        ]
        
        # Check if alarms exist and create/update if necessary
        for alarm in alarms:
            existing_alarms = cloudwatch.describe_alarms(AlarmNames=[alarm['name']])
            if existing_alarms['MetricAlarms']:
                print(f"Alarm '{alarm['name']}' already exists. Skipping creation.")
                continue

            cloudwatch.put_metric_alarm(
                AlarmName=alarm['name'],
                AlarmDescription=f'Alarm for {alarm["metric_name"]} of instance {instance_id}',
                MetricName=alarm['metric_name'],
                Namespace=alarm['namespace'],
                Statistic='Average',
                Dimensions=alarm['dimensions'],
                Period=300,  # 5 minutes
                EvaluationPeriods=1,
                DatapointsToAlarm=1,
                Threshold=85,  # Adjust threshold based on your needs
                ComparisonOperator='GreaterThanThreshold',
                TreatMissingData='missing',
                ActionsEnabled=True,
                AlarmActions=[
                    'arn:aws:sns:us-east-1:533267447870:EC2-ALARMS'
                ]
            )
            print(f"Created alarm '{alarm['name']}'.")

        # Remove the 'ALARM' tag from the instance after successful alarm creation
        ec2.delete_tags(
            Resources=[instance_id],
            Tags=[{'Key': 'ALARM'}]
        )
        print(f"Removed 'ALARM' tag from instance {instance_id}.")

        return {
            'statusCode': 200,
            'body': json.dumps('Alarms processed and \'ALARM\' tag removed successfully.')
        }
    
    except Exception as e:
        # Handle exceptions such as API call errors
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }
