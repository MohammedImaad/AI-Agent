import redis
import json
import time
import asyncio
from agent import get_graph
from langchain_core.messages import HumanMessage, AIMessage
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from dotenv import load_dotenv

r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
conversations = {}

load_dotenv()

ACCOUNT_SID = os.getenv("ACCOUNT_SID")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")

twilio_client = Client(ACCOUNT_SID, AUTH_TOKEN)

graph = None

async def initialize_graph():
    global graph
    graph = await get_graph()


def main():
    print("📬 Listening to Redis queue...")
    asyncio.run(initialize_graph())
    while True:
        task = r.lpop("chatpay_queue")
        if task:
            try:
                data = json.loads(task)
                user_number = data.get("From", "unknown").split('whatsapp:')[1]
                business_number = data.get("To","unknown").split('whatsapp:')[1]
                
                if business_number not in conversations:
                    conversations[business_number] = {
                        "user": user_number,
                        "messages": []
                    }
                
                msg_entry = {
                    "role": "human",
                    "content": data.get("Body", "")
                }
                conversations[business_number]["messages"].append(msg_entry)
                
                
                
                message_history = []
                for msg in conversations[business_number]["messages"]:
                    if msg["role"] == "human":
                        message_history.append(HumanMessage(content=msg["content"]))
                    elif msg["role"] == "ai":
                        message_history.append(AIMessage(content=msg["content"]))
                
                initial_state = {
                    "messages": message_history,  
                    "phone_number": user_number,
                    "phone_number_of_business": business_number
                }
                
                final_state = asyncio.run(graph.ainvoke(initial_state))
                ai_response = final_state["messages"][-1].content
                if isinstance(ai_response, str):
                    ai_response = ai_response.strip()
                    if ai_response.startswith('"') and ai_response.endswith('"'):
                        ai_response = ai_response[1:-1]
                ai_msg_entry = {
                    "role": "ai", 
                    "content": ai_response
                }
                conversations[business_number]["messages"].append(ai_msg_entry)

                message = twilio_client.messages.create(
                    from_='whatsapp:' + business_number,
                    to='whatsapp:' + user_number,
                    body=ai_response
                )
                twilio_resp = MessagingResponse()
                twilio_resp.message(message)
                print("✅ Message sent:", message.sid)
                #print("\n🧾 New message from queue:")
                #print(json.dumps(data, indent=2))
                #print("Conversation History:", conversations[business_number])
                
            except json.JSONDecodeError:
                print(f"⚠️ Skipped invalid JSON: {task}")
        else:
            time.sleep(1)

if __name__ == "__main__":
    main()