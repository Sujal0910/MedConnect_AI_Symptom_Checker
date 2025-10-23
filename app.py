import os
from flask import Flask, render_template, request, session, redirect, url_for
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_very_insecure_default_key_fallback")

client = None
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

if OPENROUTER_API_KEY:
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
    except Exception as e:
        print(f"Error initializing OpenRouter client: {e}")
        client = None

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'chat_history' not in session:
        session['chat_history'] = []

    if request.method == 'POST':
        if request.form.get('action') == 'clear':
            session['chat_history'] = []
            session.modified = True
            return redirect(url_for('index'))

        question = request.form['question']
        
        if not question:
            return redirect(url_for('index'))
        
        if not client:
             answer = "OpenRouter client is not initialized. Please check your API key in the .env file."
             session['chat_history'].append({"role": "user", "content": question})
             session['chat_history'].append({"role": "assistant", "content": answer})
             session.modified = True
             return redirect(url_for('index'))
        
        try:
            answer = get_openrouter_response(session['chat_history'], question, request.base_url)
            
            session['chat_history'].append({"role": "user", "content": question})
            session['chat_history'].append({"role": "assistant", "content": answer})
            session.modified = True

        except Exception as e:
            print(f"Error calling OpenRouter: {e}")
            error_message = f"An error occurred while contacting OpenRouter: {e}"
            session['chat_history'].append({"role": "user", "content": question})
            session['chat_history'].append({"role": "assistant", "content": error_message})
            session.modified = True

        return redirect(url_for('index'))

    return render_template('index.html', chat_history=session['chat_history'])

def get_openrouter_response(past_messages_list, new_prompt, site_url):
    if not client:
        raise Exception("OpenRouter client is not initialized.")

    print(f"Sending prompt to OpenRouter: {new_prompt[:50]}...")

    MODEL_NAME = "openrouter/andromeda-alpha"
    
    headers = {
        "HTTP-Referer": site_url,
    }

    messages = [{"role": "system", "content": "You are a helpful assistant."}]
    
    for message in past_messages_list:
        messages.append(message)
    
    messages.append({"role": "user", "content": new_prompt})

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        max_tokens=250,
        temperature=0.7,
        n=1,
        stop=None,
        extra_headers=headers
    )
    
    print("... Received response from OpenRouter.")
    
    if response.choices and len(response.choices) > 0:
        return response.choices[0].message.content.strip()
    else:
        return "Sorry, I couldn't get a response."

if __name__ == '__main__':
    app.run(debug=True)

