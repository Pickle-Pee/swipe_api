import re


def parse_interests(interests_str):
    return re.findall(r'\w+', interests_str)