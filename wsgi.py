import app  # this will import from app.py, not a folder

app = app.app  # reference the `Flask` app object inside app.py

if __name__ == "__main__":
    app.run()
