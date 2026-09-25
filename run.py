from pathlib import Path
import shutil
from generate_trunk_tsv import generate_trunk_tsv
from tulsa_sdr_ai.app import create_app

def main():
    if not Path("config.json").exists():shutil.copyfile("config.example.json","config.json")
    generate_trunk_tsv(); app,socketio,start=create_app("config.json"); start(); socketio.run(app,host="0.0.0.0",port=5000,allow_unsafe_werkzeug=True)
if __name__=="__main__":main()
