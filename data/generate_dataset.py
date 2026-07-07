import os
import json

# Define the 12 base scenarios with placeholders for programmatic augmentation
TEMPLATES = [
    # 1. Billing - Double Charge
    {
        "category": "billing",
        "incoming": [
            "Hi, I noticed two charges of {amount} on my credit card from Hiver on {date}. Can you please refund one? This is urgent.",
            "Hello, I was billed twice for my Hiver subscription this month. Two transactions of {amount} each on {date}. Please check and issue a refund.",
            "Hey support, why did Hiver charge me {amount} twice on {date}? I only have one shared inbox. Please revert the duplicate charge immediately.",
            "Dear support team, I see a double billing error on my card statement from {date}. Two identical charges of {amount}. Could you please look into this and process a refund?"
        ],
        "reply": [
            "Hi {name},\n\nThanks for reaching out, and sorry for the oversight! I have checked your account and confirmed that you were double-billed due to a card processing retry glitch on {date}. I have already processed a refund of {amount} to your card. You should see it reflected in your account in 3-5 business days.\n\nLet me know if you need anything else!\n\nBest regards,\n{agent_name}\nHiver Support",
            "Hello {name},\n\nApologies for the double charge! I've looked at your billing logs and see that the duplicate transaction of {amount} occurred on {date}. I have cancelled the second charge and initiated a refund. It usually takes 5-10 business days to appear on your bank statement. Let me know if you need a PDF receipt for the refund.\n\nBest,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nSo sorry for the billing mixup! You are absolutely right—our payment gateway processed two charges of {amount} on {date}. I've successfully refunded one of the charges. The refund process has been initiated and should complete in 3-5 days. Thank you for your patience!\n\nRegards,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nThank you for bringing this to our attention. I confirmed that a double billing event occurred on {date} for {amount}. I have refunded the duplicate transaction. The funds will be credited back to your original payment method within a few business days. We apologize for the inconvenience.\n\nBest,\n{agent_name}\nHiver Support"
        ],
        "metadata": [
            {"tone": "frustrated", "urgency": "high", "resolved": True},
            {"tone": "neutral", "urgency": "medium", "resolved": True},
            {"tone": "frustrated", "urgency": "high", "resolved": True},
            {"tone": "polite", "urgency": "medium", "resolved": True}
        ]
    },
    # 2. Billing - Request Invoice
    {
        "category": "billing",
        "incoming": [
            "Hi, could you please email me the invoices for the last 3 months? Our finance team needs them.",
            "Hello support, I need the PDF invoices for my Hiver account for {date} and {prev_date}. I can't find them in my dashboard.",
            "Hey Hiver, can you send over the receipts/invoices for our billing cycle on {date}? Need them for accounting.",
            "Dear Hiver support, is it possible to get historical invoices for our subscription? We require invoices from the last quarter for tax purposes."
        ],
        "reply": [
            "Hi {name},\n\nCertainly! I have gathered the PDF invoices for the last three months and attached them to this email. You can also access all historical invoices directly in Hiver by navigating to Hiver Settings > Billing > Invoice History.\n\nBest regards,\n{agent_name}\nHiver Support",
            "Hello {name},\n\nI'd be happy to help. I've attached the requested invoices for {date} and {prev_date} to this email. If you need to update your billing email address so they get forwarded automatically, please let me know!\n\nBest,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nSure thing! I have attached the receipts for your billing cycles starting from {date}. You can also download them anytime from your Admin Console under the billing section.\n\nRegards,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nI have emailed the invoices for the last quarter to your finance alias. Let me know if you need me to change the default billing email address on your account.\n\nBest,\n{agent_name}\nHiver Support"
        ],
        "metadata": [
            {"tone": "polite", "urgency": "low", "resolved": True},
            {"tone": "neutral", "urgency": "low", "resolved": True},
            {"tone": "neutral", "urgency": "low", "resolved": True},
            {"tone": "polite", "urgency": "low", "resolved": True}
        ]
    },
    # 3. Bug Report - Sync Delays
    {
        "category": "bug_report",
        "incoming": [
            "Hello, our emails are not syncing in real-time today. There is a delay of about 15 minutes, which is causing us to miss customer updates. Is there an outage?",
            "Hi support, we are noticing a major lag in incoming emails in our shared support inbox. It takes ages for emails to show up. Help!",
            "Hey Hiver team, email delivery inside our Gmail workspace seems delayed by 20 minutes. We're using Chrome on macOS. Is there a server issue?",
            "Urgent: Support email syncing is broken. Conversations are showing up late. We have clients waiting. Please fix this."
        ],
        "reply": [
            "Hi {name},\n\nI sincerely apologize for the delay. We are currently experiencing a sync backlog on our primary email processing queue. Our engineering team is actively investigating the issue. Your emails are safe and will sync as soon as the queue clears. I will keep you posted here.\n\nBest,\n{agent_name}\nHiver Support",
            "Hello {name},\n\nSorry for the delay in email syncing. We are currently experiencing a transient API issue with Gmail's push notifications, resulting in latency. We are working on a fix and expect it to be fully resolved in the next hour. All delayed emails will backfill automatically. Thank you for your patience.\n\nBest,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nThanks for reaching out. Yes, we are currently experiencing a system-wide sync latency of 15-20 minutes. Our team is resolving the database backlog now. I've flagged your account to monitor it specifically. I will write back as soon as the sync lag is resolved.\n\nRegards,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nWe apologize for this disruption. Our engineering team has identified a pipeline delay affecting real-time updates. They are deployed a patch now. We estimate full recovery within 30 minutes. I will notify you the moment sync is completely restored.\n\nBest,\n{agent_name}\nHiver Support"
        ],
        "metadata": [
            {"tone": "neutral", "urgency": "high", "resolved": False},
            {"tone": "frustrated", "urgency": "high", "resolved": False},
            {"tone": "neutral", "urgency": "high", "resolved": False},
            {"tone": "frustrated", "urgency": "high", "resolved": False}
        ]
    },
    # 4. Bug Report - Invite User Error
    {
        "category": "bug_report",
        "incoming": [
            "Hi, I'm trying to invite a new team member to our shared inbox, but every time I click invite, I get a '500 Server Error'. Can you add them for me?",
            "Hello, invitation system seems broken. I tried to add user@company.com to Hiver but got an internal server error. Please assist.",
            "Hey support, I'm getting a 500 error when trying to invite my colleague. Their email is user@company.com. Why is this happening?",
            "Dear support, I cannot add new seats to my account. Clicking the 'Invite' button displays a red error box. Please fix this bug."
        ],
        "reply": [
            "Hi {name},\n\nI apologize for the error. This 500 server error usually happens if the user's email address has an active session or was previously added to another Hiver workspace. I have manually cleared their state and successfully invited them to your workspace. They should receive the invite link shortly.\n\nBest,\n{agent_name}\nHiver Support",
            "Hello {name},\n\nI'm sorry for the friction. I investigated the logs and found a database conflict with the user's email. I have manually resolved the conflict and added user@company.com to your shared inbox. Please ask them to check their inbox for the onboarding email.\n\nBest,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nThanks for reporting this. I've manually processed the invite for your colleague. You should now see them in your Hiver Admin dashboard under pending invites. Please let me know if they face any issues logging in.\n\nRegards,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nWe apologize for the error. I have manually added the new seat to your subscription and sent the invite. You will see the update in your next billing statement. Please let us know if we can help with further setup.\n\nBest,\n{agent_name}\nHiver Support"
        ],
        "metadata": [
            {"tone": "neutral", "urgency": "medium", "resolved": True},
            {"tone": "neutral", "urgency": "medium", "resolved": True},
            {"tone": "frustrated", "urgency": "medium", "resolved": True},
            {"tone": "neutral", "urgency": "medium", "resolved": True}
        ]
    },
    # 5. Feature Request - Dark Mode
    {
        "category": "feature_request",
        "incoming": [
            "Hi Hiver team, is there any plan to support dark mode? The bright interface is really straining my eyes at night.",
            "Hello, does Hiver have a dark theme? If not, please consider this a feature request. It would be amazing.",
            "Hey support, my team really wants a dark mode theme for the shared inbox extension. Any timeline on when this might be released?",
            "Dear support, a native dark mode in Hiver would be highly appreciated. The default white template gets tiring. Thank you."
        ],
        "reply": [
            "Hi {name},\n\nThanks for reaching out! Currently, Hiver does not support a native dark mode, but we hear you—it is one of our most requested features. I have officially logged this feedback with our product team to raise its priority. In the meantime, many of our users use the 'Dark Reader' browser extension as a temporary workaround.\n\nBest regards,\n{agent_name}\nHiver Support",
            "Hello {name},\n\nThank you for the suggestion! We don't have a dark theme available yet, but it is currently on our product roadmap for later this year. I've added your account details to the notification list so we'll alert you the moment it goes live!\n\nBest,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nGreat idea! While we don't have a specific timeline for dark mode, I have passed your request along to our design team. Feedback from active teams like yours helps us decide what to build next. Thank you!\n\nRegards,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nThank you for sharing this feedback. While we don't have a native dark mode option, I've registered your vote for this feature. We are continually updating our UI, and we hope to address this soon.\n\nBest,\n{agent_name}\nHiver Support"
        ],
        "metadata": [
            {"tone": "polite", "urgency": "low", "resolved": True},
            {"tone": "polite", "urgency": "low", "resolved": True},
            {"tone": "neutral", "urgency": "low", "resolved": True},
            {"tone": "polite", "urgency": "low", "resolved": True}
        ]
    },
    # 6. Feature Request - SMS Integration
    {
        "category": "feature_request",
        "incoming": [
            "Hi, is there a way to receive SMS alerts when an email marked high priority arrives in Hiver? We need to reply instantly.",
            "Hello support, does Hiver integrate with Twilio or SMS services? We want to send text messages to our agents for critical customer issues.",
            "Hey team, does Hiver support sending SMS notifications? We need mobile alerts for offline staff when urgent queries come in.",
            "Dear support, we would like to set up SMS alerts for specific shared inbox filters. Can Hiver do this natively?"
        ],
        "reply": [
            "Hi {name},\n\nHiver does not support native SMS notifications at this time. However, you can achieve this by connecting Hiver to Twilio or your SMS provider via our Zapier integration. I have logged your request for native SMS support with our integrations team.\n\nBest,\n{agent_name}\nHiver Support",
            "Hello {name},\n\nWe don't support SMS alerts natively, but you can configure this using Hiver's webhook integrations. By setting up a webhook on new emails, you can route notifications to Twilio. Let me know if you would like some sample configuration guides for this!\n\nBest,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nThanks for reaching out. Native SMS integration isn't supported right now, but I have passed this along as a feature request to our product team. In the meantime, you can set up Slack mobile push alerts using our Slack integration which might serve a similar purpose.\n\nRegards,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nThank you for the inquiry. Hiver currently relies on email and Slack notifications. I have forwarded your request for SMS alerts to our product managers for roadmap review. Let us know if we can help you set up Slack alerts instead.\n\nBest,\n{agent_name}\nHiver Support"
        ],
        "metadata": [
            {"tone": "polite", "urgency": "medium", "resolved": False},
            {"tone": "neutral", "urgency": "medium", "resolved": False},
            {"tone": "neutral", "urgency": "medium", "resolved": False},
            {"tone": "polite", "urgency": "medium", "resolved": False}
        ]
    },
    # 7. Cancellation - Cancel and Refund
    {
        "category": "cancellation",
        "incoming": [
            "I want to cancel my Hiver subscription immediately and request a full refund. We are no longer using the tool.",
            "Hi support, please cancel our account. We'd also like a refund for the current month since we didn't use it. Thank you.",
            "Please cancel my account. We were charged yesterday but we decided to stop using Hiver. I request a refund of the charge.",
            "Hello, we need to cancel our Hiver subscription immediately. Please confirm the cancellation and refund our last payment."
        ],
        "reply": [
            "Hi {name},\n\nI have processed the cancellation of your subscription. Since you were billed recently and haven't used the tool, I have also issued a full refund of {amount} to your card. The refund will take 3-5 days. Your account will remain active in read-only mode until the end of the billing cycle.\n\nBest,\n{agent_name}\nHiver Support",
            "Hello {name},\n\nI've cancelled your subscription as requested. I have also processed a refund for the unused days of this billing cycle. You should see the credit of {amount} on your card statement within a few business days. Let me know if you need a receipt for this refund.\n\nBest,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nI have processed the cancellation and refunded your payment of {amount} from yesterday. The funds will return to your account in 3-5 business days. Your workspace data will remain accessible until the end of the month. Thank you for using Hiver!\n\nRegards,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nI have cancelled your subscription. I also initiated a refund for the billing cycle charge. It should clear in 5-10 business days. Please let us know if there is anything we could have done better.\n\nBest,\n{agent_name}\nHiver Support"
        ],
        "metadata": [
            {"tone": "frustrated", "urgency": "high", "resolved": True},
            {"tone": "neutral", "urgency": "medium", "resolved": True},
            {"tone": "frustrated", "urgency": "high", "resolved": True},
            {"tone": "neutral", "urgency": "medium", "resolved": True}
        ]
    },
    # 8. Cancellation - Data Retention
    {
        "category": "cancellation",
        "incoming": [
            "Hi, we are cancelling our account. Will this delete all our historical email threads? We need to keep a record of past chats.",
            "Hello support, if we cancel our Hiver subscription, do we lose access to all the emails in our shared folders? Or do they stay in Gmail?",
            "Hey Hiver, we're planning to cancel. Does cancellation delete the email data from Gmail, or just the Hiver labels?",
            "Dear support, please clarify what happens to our historical emails when we terminate our subscription. Will the emails be deleted?"
        ],
        "reply": [
            "Hi {name},\n\nRest assured, your emails are safe! Because Hiver runs on top of Gmail, all your emails remain in your Gmail accounts even after you cancel. Only the Hiver metadata (assignees, notes, tags) will be archived on our end, but the actual email threads will never be deleted from your Gmail.\n\nBest regards,\n{agent_name}\nHiver Support",
            "Hello {name},\n\nCancelling Hiver does not delete any of your emails from Gmail. The email threads will stay exactly where they are in your inbox. You will only lose access to the Hiver sidebar and features like email assignment and shared drafts. Let me know if you have other questions!\n\nBest,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nGood question! All your historical email data remains in Gmail. Hiver only overlays collaborative features on top of Gmail, so your core emails are never touched. You can cancel safely without losing your customer history.\n\nRegards,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nThank you for asking. When you cancel, all emails remain in your Gmail folders. We do not delete any email content. The Hiver sharing layers are removed, but the original emails stay in your account. Let us know if you need help with the cancellation process.\n\nBest,\n{agent_name}\nHiver Support"
        ],
        "metadata": [
            {"tone": "polite", "urgency": "low", "resolved": True},
            {"tone": "neutral", "urgency": "low", "resolved": True},
            {"tone": "neutral", "urgency": "low", "resolved": True},
            {"tone": "polite", "urgency": "low", "resolved": True}
        ]
    },
    # 9. Onboarding - Assign Conversation
    {
        "category": "onboarding",
        "incoming": [
            "Hi, I'm new to Hiver. How do I assign an email to one of my teammates? I can't find the assign button.",
            "Hello support, how do I delegate a conversation to someone else? I need a quick step-by-step guide.",
            "Hey team, where is the option to assign an email to a teammate? I see the shared inbox but not the assign options.",
            "Dear support, could you explain how the email assignment feature works? How do I assign a ticket to a colleague?"
        ],
        "reply": [
            "Hi {name},\n\nWelcome to Hiver! To assign an email, open the thread in Gmail. You will see the Hiver sidebar on the right. Click the 'Assignee' dropdown field, select or search for your colleague, and click save. The email will automatically appear in their 'Assigned to me' tab.\n\nBest,\n{agent_name}\nHiver Support",
            "Hello {name},\n\nGlad to have you onboard! You can assign an email by clicking the 'Assign' dropdown in the Hiver panel on the right side of the open email. Just choose your colleague's name, and they'll be notified immediately. Let me know if you would like a quick screenshare demo!\n\nBest,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nTo assign an email: 1. Open the thread in Gmail. 2. Look at the Hiver panel on the right. 3. Click the dropdown under 'Assignee' and pick a team member. You can also assign it to yourself by clicking the 'Claim' button at the top.\n\nRegards,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nTo delegate a conversation, open the thread and use the Hiver widget on the right. Select your colleague from the 'Assignee' field. They will receive a notification and the email will show up in their Hiver inbox. Let us know if you need help with setting up auto-assignment filters.\n\nBest,\n{agent_name}\nHiver Support"
        ],
        "metadata": [
            {"tone": "polite", "urgency": "low", "resolved": True},
            {"tone": "neutral", "urgency": "low", "resolved": True},
            {"tone": "neutral", "urgency": "low", "resolved": True},
            {"tone": "polite", "urgency": "low", "resolved": True}
        ]
    },
    # 10. Onboarding - Gmail Forwarding
    {
        "category": "onboarding",
        "incoming": [
            "Hi, I'm trying to set up our support shared inbox but I'm stuck on the Gmail forwarding step. It's not verifying. Help!",
            "Hello support, the forwarding verification code from Gmail is not arriving in Hiver. How can I verify our forwarding address?",
            "Hey team, we're setting up forwarding from support@company.com to Hiver, but we're not receiving the confirmation email. Please assist.",
            "Dear Hiver support, we are onboarding our team but cannot verify forwarding. Gmail requires a code we can't find. Where is the verification code?"
        ],
        "reply": [
            "Hi {name},\n\nNo worries, this is a common onboarding step! When Gmail sends the verification code, it arrives in your Hiver Admin dashboard under Settings > Shared Inboxes > Forwarding Verification. I have manually retrieved your code and verified the forwarding on our end. You are good to go!\n\nBest,\n{agent_name}\nHiver Support",
            "Hello {name},\n\nI have manually checked your sync logs and verified the forwarding setup for support@company.com. You don't need the verification code anymore. Please refresh your Gmail, and you should see Hiver start syncing emails!\n\nBest,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nI've got you covered! I found the Gmail verification email in our logs. The verification code is: 123-456-789. Please paste this into your Gmail forwarding settings to complete the setup. Let me know if you hit any other bumps!\n\nRegards,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nI have approved the forwarding verification request from our backend. Gmail forwarding is now active for your workspace. Please check if new emails are appearing in the Hiver shared folder. Let us know if we can help with anything else.\n\nBest,\n{agent_name}\nHiver Support"
        ],
        "metadata": [
            {"tone": "neutral", "urgency": "medium", "resolved": True},
            {"tone": "neutral", "urgency": "medium", "resolved": True},
            {"tone": "polite", "urgency": "medium", "resolved": True},
            {"tone": "polite", "urgency": "medium", "resolved": True}
        ]
    },
    # 11. Integration - Slack Issues
    {
        "category": "integration",
        "incoming": [
            "Hi, our Slack integration suddenly stopped working today. We are not getting any notifications in our #support channel when emails are assigned.",
            "Hello support, we re-auth'd Slack yesterday but today the notifications are not posting. Is there a bug?",
            "Hey support team, the Hiver to Slack notification bridge seems broken. We verified our Slack webhook is active. What should we do?",
            "Dear Hiver, we are not receiving Slack notifications for new emails. This started happening after the updates yesterday. Please fix this."
        ],
        "reply": [
            "Hi {name},\n\nI'm sorry for the interruption. We had an API token expiration issue with our Slack integration app earlier today. Please go to Hiver Settings > Integrations > Slack, click 'Disconnect', and then 'Reconnect' to re-authorize. This will refresh the tokens and restore notifications instantly.\n\nBest,\n{agent_name}\nHiver Support",
            "Hello {name},\n\nThanks for reaching out. I checked the integration logs and see that the webhook is returning a 403 Forbidden error. This means the Slack channel permissions might have changed. Could you please try reconnecting Hiver in Slack to refresh the permissions? Let me know if that works.\n\nBest,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nI apologize for the Slack issue. I have cleared the cache for your integration from our backend. Please disconnect and reconnect the Slack integration in your Hiver dashboard. This should resolve the notification lag immediately.\n\nRegards,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nWe apologize for this bug. We resolved an issue with our Slack notification queue. Your notifications should now be delivering. If they are still missing, please try re-authenticating the Slack connection from the Admin panel.\n\nBest,\n{agent_name}\nHiver Support"
        ],
        "metadata": [
            {"tone": "frustrated", "urgency": "high", "resolved": True},
            {"tone": "neutral", "urgency": "medium", "resolved": True},
            {"tone": "neutral", "urgency": "medium", "resolved": True},
            {"tone": "frustrated", "urgency": "high", "resolved": True}
        ]
    },
    # 12. Integration - Zapier Filters
    {
        "category": "integration",
        "incoming": [
            "Hi, how do I configure Hiver's Zapier integration so it only triggers when an email is assigned to a specific tag, like 'Refund'?",
            "Hello, does the Hiver Zapier trigger support custom fields or tags? We want to filter events before sending them to Salesforce.",
            "Hey team, we're building a Zap using Hiver. Can we filter based on Hiver labels? We need to route specific tagged emails to Jira.",
            "Dear support, how do we set up conditional filters in Zapier for Hiver emails? We only want to trigger Zaps for resolved emails."
        ],
        "reply": [
            "Hi {name},\n\nYes, absolutely! In your Zapier setup, choose 'New Email Tagged' as the Hiver trigger. Then, in the trigger configuration, select 'Refund' from the tag list. This ensures the Zap only runs when that specific tag is applied. Let me know if you need help with subsequent Salesforce steps!\n\nBest,\n{agent_name}\nHiver Support",
            "Hello {name},\n\nYes, the Hiver Zapier integration exposes tags and assignees. You can add a 'Filter by Zapier' step right after the Hiver trigger. In the filter, set the condition to match the Hiver 'tag' or 'assignee' field before sending data to Salesforce. Let me know if you need a walkthrough.\n\nBest,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nYes, Hiver passes all labels and tags to Zapier! When setting up your Zap, use the 'New Email Tagged' trigger and choose your Jira-routing tag. This will filter out other emails automatically. Let us know if you need help!\n\nRegards,\n{agent_name}\nHiver Support",
            "Hi {name},\n\nTo trigger Zaps only for resolved emails, use the Hiver 'Email Status Changed' trigger in Zapier. Then, add a Zapier filter step where 'New Status' exactly matches 'Resolved'. This will filter out open or pending status updates. Let us know if you need anything else.\n\nBest,\n{agent_name}\nHiver Support"
        ],
        "metadata": [
            {"tone": "polite", "urgency": "low", "resolved": True},
            {"tone": "neutral", "urgency": "low", "resolved": True},
            {"tone": "neutral", "urgency": "low", "resolved": True},
            {"tone": "polite", "urgency": "low", "resolved": True}
        ]
    }
]

def main():
    print("Generating dataset using programmatic template augmentation...")
    os.makedirs("data", exist_ok=True)
    
    output_file = "data/emails.jsonl"
    
    # Helper lists for programmatic variables
    names = ["John Doe", "Sarah Jenkins", "Michael Chang", "Emily Watson"]
    agent_names = ["Alice", "Bob", "Charlie", "David"]
    dates = ["July 5th", "July 6th", "July 7th", "July 7th"]
    prev_dates = ["June", "May", "April", "March"]
    amounts = ["$29", "$49", "$99", "$129"]
    plans = ["Growth", "Pro", "Enterprise", "Elite"]
    companies = ["Acme Corp", "TechStart Inc", "GlobalLogistics", "DesignStudio"]

    generated_count = 0
    
    with open(output_file, "w", encoding="utf-8") as f:
        # Loop through our 12 template configurations
        for template_idx, template in enumerate(TEMPLATES):
            category = template["category"]
            
            # Create 4 variations for each template configuration = 48 items
            for var_idx in range(4):
                name = names[var_idx]
                agent_name = agent_names[var_idx]
                date = dates[var_idx]
                prev_date = prev_dates[var_idx]
                amount = amounts[var_idx]
                plan = plans[var_idx]
                company = companies[var_idx]
                
                # Format placeholders in incoming and reply
                incoming_raw = template["incoming"][var_idx]
                reply_raw = template["reply"][var_idx]
                
                incoming_text = incoming_raw.format(
                    amount=amount,
                    date=date,
                    prev_date=prev_date,
                    company=company
                )
                
                sent_reply = reply_raw.format(
                    name=name.split()[0], # First name
                    agent_name=agent_name,
                    date=date,
                    prev_date=prev_date,
                    amount=amount,
                    plan=plan,
                    company=company
                )
                
                metadata = template["metadata"][var_idx]
                metadata["variation_id"] = var_idx + 1
                
                data_point = {
                    "id": f"email_{generated_count + 1:03d}",
                    "category": category,
                    "incoming_email": incoming_text,
                    "sent_reply": sent_reply,
                    "metadata": metadata
                }
                
                f.write(json.dumps(data_point) + "\n")
                generated_count += 1

    print(f"Dataset generation complete! Generated {generated_count} pairs in {output_file}.")

if __name__ == "__main__":
    main()
