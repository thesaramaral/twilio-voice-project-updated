#!/usr/bin/env python

import os
import re

from dotenv import load_dotenv
from faker import Faker
from flask import Flask, Response, jsonify, redirect, request
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import Dial, Gather, VoiceResponse
from twilio.jwt.taskrouter.capabilities import WorkerCapabilityToken



from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from flask import render_template

from twilio.jwt.access_token import AccessToken
from flask import render_template



load_dotenv()
print("TWILIO_ACCOUNT_SID:", os.getenv("TWILIO_ACCOUNT_SID"))
print("TWILIO_CALLER_ID:", os.getenv("TWILIO_CALLER_ID"))
print("TWILIO_TWIML_APP_SID:", os.getenv("TWILIO_TWIML_APP_SID"))
print("API_KEY:", os.getenv("API_KEY"))
print("API_SECRET:", os.getenv("API_SECRET"))

app = Flask(__name__)
fake = Faker()
alphanumeric_only = re.compile("[\W_]+")
phone_pattern = re.compile(r"^[\d\+\-\(\) ]+$")

twilio_number = os.environ.get("TWILIO_CALLER_ID")

# Store the most recently created identity in memory for routing calls
IDENTITY = {"identity": ""}

# Configure TaskRouter
client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["API_KEY"], os.environ["API_SECRET"])
workspace_sid = os.environ["TWILIO_TASKROUTER_WORKSPACE_SID"]

english_worker_sid = os.environ["TWILIO_ENGLISH_WORKER_SID"]
spanish_worker_sid = os.environ["TWILIO_SPANISH_WORKER_SID"]

workflow_sid = os.environ["TWILIO_WORKFLOW_SID"]

account_sid = os.environ["TWILIO_ACCOUNT_SID"]
application_sid = os.environ["TWILIO_TWIML_APP_SID"]
api_key = os.environ["API_KEY"]
api_secret = os.environ["API_SECRET"]



@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/token", methods=["GET"])
def token():
    # get credentials for environment variables
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    application_sid = os.environ["TWILIO_TWIML_APP_SID"]
    api_key = os.environ["API_KEY"]
    api_secret = os.environ["API_SECRET"]

    # Generate a random user name and store it
    identity = alphanumeric_only.sub("", fake.user_name())
    IDENTITY["identity"] = identity

    # Create access token with credentials
    token = AccessToken(account_sid, api_key, api_secret, identity=identity)

    # Create a Voice grant and add it to the token
    voice_grant = VoiceGrant(
        outgoing_application_sid=application_sid,
        incoming_allow=True,
    )
    token.add_grant(voice_grant)

    # Return token info as JSON
    token = token.to_jwt()

    # Return token info as JSON
    return jsonify(identity=identity, token=token)


@app.route("/voice", methods=["POST"])
def voice():
    resp = VoiceResponse()
    if request.form.get("To") == twilio_number:
        # Receiving an incoming call to our Twilio number
        gather = Gather(num_digits=1, action="/handle-language-selection", method="POST")
        gather.say("Thank you for calling. For Spanish, press 1. For English, press 2.")
        resp.append(gather)
    elif request.form.get("To"):
        # Placing an outbound call from the Twilio client
        dial = Dial(caller_id=twilio_number)
        # wrap the phone number or client name in the appropriate TwiML verb
        # by checking if the number given has only digits and format symbols
        if phone_pattern.match(request.form["To"]):
            dial.number(request.form["To"])
        else:
            dial.client(request.form["To"])
        resp.append(dial)
    else:
        resp.say("Thanks for calling!")

    return Response(str(resp), mimetype="text/xml")

@app.route("/handle-language-selection", methods=["POST"])
def handle_language_selection():
    selected_language = request.form.get("Digits")
    
    if selected_language == "1":
        language_worker_sid = os.environ["YOUR_SPANISH_TASK_QUEUE_SID"]
    else:
        language_worker_sid = os.environ["YOUR_ENGLISH_TASK_QUEUE_SID"]

    task = client.taskrouter.workspaces(workspace_sid).tasks.create(
        task_channel="voice",
        workflow_sid=workflow_sid,
        attributes='{"selected_language": "' + selected_language + '"}',
        task_channel_unique_name=IDENTITY["identity"]
    )

    client.taskrouter.workspaces(workspace_sid).tasks(task.sid).task_channels("voice").update(
        assignment_status="reserved",
        worker_sid=language_worker_sid
    )

    resp = VoiceResponse()
    with resp.enqueue(None, workflowSid=workflow_sid) as e:
        e.task('{"selected_language":"' + selected_language + '"}')
    resp.say("Connecting you to an available agent. Please wait.")
    return str(resp)

@app.route("/agents", methods=['GET'])
def generate_view():
    worker_sid = request.args.get('WorkerSid')
    worker_token = get_worker_token(worker_sid)

    return render_template('agent.html', worker_token=worker_token)

def get_worker_token(worker_sid):
    # Retrieve the necessary credentials and generate the token

    worker_capability = WorkerCapabilityToken(account_sid, api_key, workspace_sid, worker_sid)
    worker_capability.allow_update_activities()
    worker_capability.allow_update_reservations()

    worker_token = worker_capability.to_jwt()

    return worker_token


@app.route("/taskrouter/event", methods=["POST"])
def taskrouter_event():
    event = request.get_json()
    print(event)

    return jsonify(success=True)

@app.route("/make-call", methods=["POST"])
def make_call():
    random_number = "+1234567890"
    resp = VoiceResponse()
    dial = Dial()
    dial.number(random_number)
    resp.append(dial)
    return Response(str(resp), mimetype="text/xml")

@app.route("/select-agent", methods=["POST"])
def select_agent():
    agent_sid = request.form.get("agent_sid")
    return "Agent selected: {}".format(agent_sid)

@app.route("/incoming-call", methods=["POST"])
def incoming_call():
    resp = VoiceResponse()
    resp.say("Incoming call from task queue")
    return Response(str(resp), mimetype="text/xml")

@app.route("/update-agent-status", methods=["POST"])
def update_agent_status():
    agent_sid = request.form.get("agent_sid")
    status = request.form.get("status")
    return "Agent {} status updated: {}".format(agent_sid, status)



if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
