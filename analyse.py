import requests
import re
import os
import json
from typing import List, Tuple
from pydantic import BaseModel, parse_obj_as
from dotenv import load_dotenv
from settings import SKIPERS


load_dotenv()


class Repo(BaseModel):
    name: str
    full_name: str
    url: str
    fork: bool


REGEX = "mongodb\+srv://[a-zA-z0-9]+:.+@[a-zA-z0-9.]+mongodb\.net"



def customGet(url: str) -> requests.Response:
    # for higher rate limit 5k/hr
    response = requests.get(url, auth=(os.environ['GIT_UNAME'], os.environ['GIT_PASS']))
    # else use without auth 60 per hr
    # response = requests.get(url)
    print(f"Limit: {response.headers.get('x-ratelimit-remaining')}")
    return response


class GithubAPI:

    def getAllReposList(self, username):
        """
        Get all repos from Github
        """
        url = f"https://api.github.com/users/{username}/repos"
        response = customGet(url)
        repos = response.json()

        repos_list: List[Repo] = parse_obj_as(List[Repo], repos)
        
        return repos_list

    
class MongodbSecretChecker:

    def _checkFile(self, file):
        """
        Check for secret from file
        """
        
        filename: str = file['filename']
        for skip in SKIPERS['mid']:
            if skip in filename:
                return []

        for skip in SKIPERS['end']:
            if filename.endswith(skip):
                return []

        print(f"\tChecking file {filename}")
        
        blob_url = file['blob_url']
        txt = file.get('patch', '')
        secret_occured: List[Tuple[str, str]] = []
        for line in txt.splitlines():
            if line[0] != '+':
                continue
            rexp = re.search(REGEX, line)
            if rexp:
                secret = rexp.group()
                print("+++++++++++")
                print("got", secret)
                print("+++++++++++")
                secret_occured.append((secret, blob_url))

        return secret_occured


    def _checkAllFiles(self, files):
        """
        Check all file from files
        """
        secret_occured: List[str] = []
        for file in files:
            secret_occured.extend(self._checkFile(file))

        return secret_occured


    def _checkCommits(self, commit_url):
        print("Commit:", commit_url)
        response = customGet(commit_url)
        commits = response.json()

        all_occ = self._checkAllFiles(commits['files'])

        if commits['parents']:
            next_url = commits['parents'][0]['url']
        else:
            next_url = None
        return all_occ, next_url


    def _checkAllCommits(self, commit_url):
        """
        Check all commits from commit_url
        """
        next_url = commit_url

        secret_occured: List[str] = []

        while next_url:
            all_occ, next_url = self._checkCommits(next_url)
            secret_occured.extend(all_occ)

        return secret_occured

    
    def _checkAllBranchesFromURL(self, repo_url):
        """
        Check all branches from repo
        """
        response = customGet(repo_url)
        branches = response.json()

        secret_occured: List[str] = []
        for branch in branches:
            secret_occured.extend(self._checkAllCommits(branch["commit"]["url"]))
        return secret_occured


    def _checkAllBranches(self, repo: Repo):
        """
        Check all branches from repo
        """
        url = f"https://api.github.com/repos/{repo.full_name}/branches"
        return self._checkAllBranchesFromURL(url)


    def checkAllRepos(self, username):
        """
        Check all repos for particular user
        """
        repos = GithubAPI().getAllReposList(username)
        secret_occured: List[str] = []
        for repo in repos:
            if repo.fork and SKIPERS['fork']:
                continue
            print("starting check for", repo.full_name)
            sec_got = self._checkAllBranches(repo)
            secret_occured.extend(sec_got)
            print("got:", sec_got)
        return secret_occured


checker = MongodbSecretChecker()
uname = 'abhishek0220'
secrets = checker.checkAllRepos(uname)


print(secrets)

with open("data/"+uname + '.json', 'w') as f:
    dat = json.dumps({"result": secrets}, indent=4)
    f.write(dat)
