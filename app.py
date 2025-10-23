import os
from flask import Flask, render_template, request, session, redirect, url_for
from openai import OpenAI  # We still use the OpenAI library
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

app = Flask(__name__)

# --- ADD A SECRET KEY (REQUIRED FOR SESSION) ---
# Get it from environment or use a default (default is INSECURE for production)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_very_insecure_default_key_fallback")
# ---------------------------------------------


# --- MODIFICATION FOR OPENROUTER ---
# We now get the OpenRouter API key
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Set the base URL to OpenRouter's
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# -----------------------------------

try:
    if not OPENROUTER_API_KEY:
        print("OPENROUTER_API_KEY not set in .env file. The app may not work.")
        client = None
    else:
        # Initialize the OpenAI client to point to OpenRouter
        client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=OPENROUTER_API_KEY,
        )
except Exception as e:
    print(f"Error initializing OpenRouter client: {e}")
    client = None

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Main route for the application.
    Handles both GET (display page) and POST (submit question) requests.
    """
    # Initialize chat history in session if it doesn't exist
    if 'chat_history' not in session:
        session['chat_history'] = []

    if request.method == 'POST':
        # Handle clearing the chat history
        if request.form.get('action') == 'clear':
            session['chat_history'] = []
            session.modified = True
            return redirect(url_for('index'))

        question = request.form['question']
        
        if not question:
            # Don't do anything if the question is empty
            return redirect(url_for('index'))
        
        if not client:
             answer = "OpenRouter client is not initialized. Please check your API key in the .env file."
             session['chat_history'].append({"role": "user", "content": question})
             session['chat_history'].append({"role": "assistant", "content": answer})
             session.modified = True
             return redirect(url_for('index'))
        
        try:
            # Pass the *current* chat history and new question to the function
            answer = get_openrouter_response(session['chat_history'], question, request.base_url)
            
            # Add both question and answer to the session history
            session['chat_history'].append({"role": "user", "content": question})
            session['chat_history'].append({"role": "assistant", "content": answer})
            session.modified = True

        except Exception as e:
            print(f"Error calling OpenRouter: {e}")
            error_message = f"An error occurred while contacting OpenRouter: {e}"
            session['chat_history'].append({"role": "user", "content": question})
            session['chat_history'].append({"role": "assistant", "content": error_message})
            session.modified = True

        # Redirect back to the index page (GET request)
        # This is the Post-Redirect-Get (PRG) pattern
        return redirect(url_for('index'))

    # GET request: Render the template with the chat history
    return render_template('index.html', chat_history=session['chat_history'])

def get_openrouter_response(past_messages_list, new_prompt, site_url):
    """
    Calls the OpenRouter API with the user's prompt AND the chat history.
    """
    if not client:
        raise Exception("OpenRouter client is not initialized.")

    print(f"Sending prompt to OpenRouter: {new_prompt[:50]}...")

    # --- MODIFICATION FOR OPENROUTER ---
    # We now specify a model from OpenRouter.
    # Let's use a free model to start!
    # You can find more models at: https://openrouter.ai/models
    #
    # Some great FREE models to try:
    # NOTE: The model 'mistralai/mistral-7b-instruct-free' seems to be no longer valid.
    # We will use 'google/gemma-7b-it:free' instead.
    #
    # - "google/gemma-7b-it:free"
    # - "meta-llama/llama-3-8b-instruct:free"
    #
    MODEL_NAME = "openrouter/andromeda-alpha" # <-- UPDATED MODEL
    
    # OpenRouter recommends sending these headers
    headers = {
        "HTTP-Referer": site_url, # Your app's URL
        "X-Title": "Flask Chatbot Test", # Your app's name
    }
    # -----------------------------------

    # --- BUILD CONTEXT-AWARE MESSAGES ---
    messages = [{"role": "system", "content": "You are a helpful assistant."}]
    
    # Add past messages from history
    for message in past_messages_list:
        # We already stored them in the correct format!
        messages.append(message)
    
    # Add the new user prompt
    messages.append({"role": "user", "content": new_prompt})
    # ------------------------------------

    # Create the chat completion request
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages, # Pass the full conversation
        max_tokens=250,
        temperature=0.7,
        extra_headers=headers # Pass the recommended headers
    )

    print("Received response from OpenRouter.")
    
    # Extract and return the text content from the response
    return response.choices[0].message.content.strip()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)




