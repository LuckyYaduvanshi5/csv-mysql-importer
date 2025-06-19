from app import app, socketio

if __name__ == '__main__':
    print("🚀 Starting CSV to MySQL Importer Web App...")
    print("📱 Access the app at: http://localhost:5000")
    print("🌐 For public access, deploy to cloud platforms like Heroku, Vercel, or Railway")
    
    socketio.run(app, 
                debug=False, 
                host='0.0.0.0', 
                port=5000,
                allow_unsafe_werkzeug=True)
