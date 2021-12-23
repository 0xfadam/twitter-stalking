Prerequisites:
gem + twurl : https://github.com/twitter/twurl


1. Create DB
python3 script.py --create

2. Add someone
python3 script.py --insert --influencer toto

3. Make crontab to synchronize
0 */2 * * * python3 /opt/stalking/script.py --global_synchronize
