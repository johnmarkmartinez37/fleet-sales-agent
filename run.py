from app import create_app
from config import PORT, DEBUG

app = create_app()

if __name__ == "__main__":
    print("=" * 50)
    print("  Fleet Sales Intelligence Portal")
    print(f"  Running at: http://localhost:{PORT}")
    print("  Press Ctrl+C to stop")
    print("=" * 50)
    app.run(debug=DEBUG, port=PORT)