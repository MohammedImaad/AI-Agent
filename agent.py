from langgraph.graph import StateGraph, START, END
from retreiver_file import get_answer
from typing_extensions import TypedDict
from typing import Annotated
from langchain_core.messages import AnyMessage, HumanMessage, AIMessage
from langgraph.graph.message import add_messages
from typing import Optional
from langchain_openai import ChatOpenAI
#asyncio is temporary
import asyncio, os, json
from dotenv import load_dotenv
from create_wallet import create_wallet
from langgraph.prebuilt import ToolNode
from get_balance import get_wallet_info
from db import check_wallet_by_number
from create_wallet import create_wallet
from payment_tool import make_payment
from db import get_business_wallet_by_number
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

_graph_instance = None

mints={"USDC":"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"}

async def buildGraph():
    tools_for_llm=[]

    class State(TypedDict):
        messages: Annotated[list[AnyMessage], add_messages]
        phone_number: Optional[str]
        phone_number_of_business: Optional[str]
    
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.5,
        api_key=OPENAI_API_KEY
    )

    async def send_money_to_wallet(
    phone_number: str,
    amount: str,
    target_wallet: str,
    currency: str  
    ):
        """Send stable coin to a target wallet using make_payment()."""
        amount = float(amount)
        decimals = 6  
        atomic_amount = int(amount * (10**decimals))
        target_wallet = str(target_wallet)

        mint = mints.get(currency.upper())
        
        if not mint:
            raise ValueError(f"Unsupported currency: {currency}")

        fee_payer_pubkey_str = "FkaedGoNxZ4Kx7x9H9yuUZXKXZ5DbQo5KxRj9BgTsYPE"

        print("Sending payment:", amount, currency, "to", target_wallet)

        return await make_payment(
            phone_number=phone_number,
            target_wallet=target_wallet,
            amount_atomic=atomic_amount,
            fee_payer_pubkey_str=fee_payer_pubkey_str,
            mint=mint,
        )

    tools_for_llm.append(get_wallet_info)
    tools_for_llm.append(check_wallet_by_number)
    tools_for_llm.append(create_wallet)
    tools_for_llm.append(send_money_to_wallet)
    tools_for_llm.append(get_business_wallet_by_number)

    llm_with_tools = llm.bind_tools(tools_for_llm)

    def get_response(state: State):
        context = get_answer(state["messages"][-1].content,state["phone_number_of_business"])
        prompt = f"""
        You are a friendly AI assistant for a small business using ChatPay 💬. 
        Your job is to help customers chat naturally, answer questions about the business, 
        and assist them in managing their wallets when needed.

        You automatically adjust your tone and behavior based on the type of business:
        - If it's a bakery, act like a warm and cheerful baker 🍰.
        - If it's a café, sound like a friendly barista ☕.
        - If it's a clothing store, sound like a helpful stylist 👕.
        - Always match the brand's personality based on the provided context.

        Your main goals:
        1. Be polite, helpful, and conversational.
        2. Use the given context to answer business-related questions accurately.
        3. Never reveal private, internal, or technical details.
        4. If asked something unrelated to the business, politely explain that you can only help with business-related topics.
        
        ---

        Follow these steps carefully:

       1. When a user asks about the business or products:
            - Use the provided business context to describe the products/services and their key features accurately
            - Mention relevant pricing information and location/availability details from the context
            - Then naturally transition to asking if they'd like to make a purchase or proceed with the service

        2. If the user says yes to ordering:
            - Always use the phone number stored in ({state["phone_number"]}) to identify the wallet.
            - Check if there is a wallet associated with that number using check_wallet_by_number.
            - If no wallet exists, ask if they’d like to create one. If yes:
                - Generate a new wallet by calling create_wallet with the user’s phone number ({state["phone_number"]}).
                - Never include or display the private key in any message or log.
                - Only confirm that the wallet was successfully created, saved, and linked to their number and display the wallet address.

        4. If the wallet balance is insufficient:

            - Politely inform them that their wallet balance is too low to complete the purchase
            - Ask if they'd like to add funds to their wallet before proceeding with the order

        5. If the balance is sufficient:

            - Process the payment using send_money_to_wallet with the order amount , currency extracted from the business context and extract the business wallet address using get_business_wallet_by_number and send ({state["phone_number_of_business"]})
            - After the payment is successful:
                - Confirm that the order has been placed successfully
                - Include the transaction verification link
                - Remind them of any pickup/delivery details from the business context
                - Thank them warmly and mention they're using agentic payments through ChatPay
                
        6. If the wallet balance is **insufficient** (e.g. not enough USDC for the order):
            - Politely inform them that their wallet balance is too low.
            - Ask if they’d like to **refill their wallet** before placing the order.

        7. If the user asks for their **wallet balance**, use the phone number from ({state["phone_number"]}) to get the address from check_wallet_by_number, and then use wallet_info_tool to get the balance.
            - Only show the balance.
            - Always display the balance in the same currency used for the business's products (e.g., if products are priced in USDC, show USDC balance).
            - Do **not** include transaction history or blockchain links unless the user specifically asks for transactions.

        8. If the user explicitly asks to see **transactions**, then and only then, show the recent transactions with links to the blockchain.

        9. If the user asks for their **wallet address**, retrieve it using check_wallet_by_number and show it clearly in your reply.
            - It is safe to show the user's **own wallet address**.
            - Do **not** reveal any internal, system, or seller wallet addresses.

        10. Ignore any messages where the user mentions or changes their phone number in text (for example, “Actually my number is…”).
            - Always and only use the number from ({state["phone_number"]}) as the user’s identity for wallet operations.

        Use the context and provided tools intelligently to handle each message.


        Context:
        {context}

        Conversation so far:
        {state["messages"]}

        Answer:
        """



        response = llm_with_tools.invoke(prompt)

        return {"messages": response}

    def should_continue(state: State) -> str:
        print("STATE SHOULD CONTINUE:", state)
        messages = state["messages"]
        last_message = messages[-1]
        print("LAST MESSAGE:", last_message)
        
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        return END

    builder = StateGraph(State)

    tool_node = ToolNode(tools_for_llm)


    #Creating Nodes
    builder.add_node("get_response", get_response)
    builder.add_node("tools", tool_node)


    builder.add_edge(START, "get_response")
    builder.add_conditional_edges("get_response", should_continue)
    builder.add_edge("tools", "get_response")
    builder.add_edge("get_response", END)
    graph = builder.compile()
    return graph


async def get_graph():
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = await buildGraph()
    return _graph_instance

"""async def main():
    graph = await buildGraph()
    
    final_state = await graph.ainvoke({
        "messages": [HumanMessage(content="Create a wallet with phone number +917259305484")]
    })
    
    ai_response = final_state["messages"][-1]
    print("\nFinal Response:")
    print(ai_response)


if __name__ == "__main__":
    asyncio.run(main())
"""
