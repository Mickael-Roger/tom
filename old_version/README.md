# Installation

```
# (optional) Create a python virtualenv
python3 -m venv /tmp/tom
source /tmp/tom/bin/activate

# Install the required python modules
pip3 install -r requirements.txt

# Edit/create you config.yml file

# Run tom

python3 server.py

```
docker build -t tom:current .; sudo systemctl restart tom; sleep 5; docker logs -f tom
