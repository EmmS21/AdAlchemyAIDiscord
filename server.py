#!/usr/bin/env python3
import os
import threading
import http.server
import socketserver

# Use the PORT environment variable set by Cloud Run
PORT = int(os.getenv('PORT', 8080))

# Define a simple request handler
class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Discord bot is running")

# Function to start the simple HTTP server
def start_server():
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving HTTP on port {PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    try:
        # Log environment variables to verify they are set
        print(f"DISCORD_TOKEN: {os.getenv('DISCORD_TOKEN')}")
        print(f"CONNECTION_STRING: {os.getenv('CONNECTION_STRING')}")

        # Start the HTTP server in a separate thread
        server_thread = threading.Thread(target=start_server)
        server_thread.start()
        
        # Simulate Discord bot initialization (to be replaced with actual bot logic)
        print("Starting Discord bot...")
        # Placeholder for actual bot initialization
        # Example: runBot.client.run(os.getenv('DISCORD_TOKEN'))
    except Exception as e:
        print(f"An error occurred: {e}")
