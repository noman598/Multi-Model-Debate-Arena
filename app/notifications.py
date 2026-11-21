# AWS SNS MIGRATION NOTE:
# To migrate to Amazon SNS, replace the print below with:
# sns = boto3.client('sns')
# sns.publish(TopicArn=SNS_TOPIC_ARN, Message=f"Photo {filename} processed for user {user_id}")


def send_photo_notification(user_id: int, photo_id: int, filename: str) -> None:
    """Notification service: prints to console for demo, swappable with AWS SNS."""
    print(f"\n==========================================")
    print(f"🔔 [NOTIFICATION] Photo processed successfully!")
    print(f"   User ID : {user_id}")
    print(f"   Photo ID: {photo_id}")
    print(f"   Filename: {filename}")
    print(f"==========================================\n", flush=True)
