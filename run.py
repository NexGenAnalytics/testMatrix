#!/usr/bin/env python

import re, sys, os, time, yaml, json
import numpy as np
from argparse import ArgumentParser
import shutil, subprocess

def dicToJsonFile(dic, mode):
  with open("test.json", mode) as file:
    json_string = json.dumps(dic, default=lambda o: o.__dict__, sort_keys=True, indent=2)
    file.write(json_string)

def printDic(d):
  for k,v in d.items():
    print(k, v)

def readPackFile():
  packDic = {}
  file1 = open('packages.txt', 'r')
  count = -1
  while True:
    count+=1
    line = file1.readline()
    if not line:
      break

    lnlist = line.split()
    name      = lnlist[0]
    subdir    = lnlist[1]
    stability = lnlist[2]
    classif   = lnlist[3]

    packDic[name] = {"name": name,
                     "index": count,
                     "subdir": subdir,
                     "stability": stability,
                     "class": classif}

  file1.close()
  return packDic

def createNodesList(packDic):
  myl = []
  for k,v in packDic.items():
    newd = {"index": v["index"],
            "name":  v["name"],
            "class": v["class"],
            "stability": v["stability"],
            "numsubpack": v["numsubpack"],
            "loc": v["loc"]}
    myl.append(newd)
  return myl

def createLinksList(packDic):
  myl = []
  for k,v in packDic.items():
    currentPackIndex = nameToIndex(k, packDic)
    print(k, currentPackIndex)
    print(v)

    currRequiredDeps = v["req-deps"]
    print(len(currRequiredDeps))
    if len(currRequiredDeps) > 0:
      for it in currRequiredDeps:
        if it != k:
          tmpd = {"source": currentPackIndex,
                  "target": nameToIndex(it, packDic),
                  "value": 10.0}
          myl.append(tmpd)

    currOptionalDeps = v["opt-deps"]
    if len(currOptionalDeps) > 0:
      for it in currOptionalDeps:
        if it != k:
          tmpd = {"source": currentPackIndex,
                  "target": nameToIndex(it, packDic),
                  "value": 1.0}
          myl.append(tmpd)

  return myl

def nameToIndex(name, packDic):
  return packDic[name]["index"]

def findNeededPackages(strings, allPackNames):
  result = []
  for it in allPackNames:
    substring_in_list = any(it in sstr for sstr in strings)
    if substring_in_list:
      result.append(it)
  return result

def hasSubpackages(depFileContent):
  re0  = re.compile(r'SUBPACKAGES_DIRS')
  res0 = re.search(re0, depFileContent)
  re1  = re.compile(r'TRIBITS_PACKAGE_DEFINE_DEPENDENCIES')
  res1 = re.search(re1, depFileContent)
  return (res0 != None and res1 != None)

def getSubpackagesDirNames(depFile):
  result = []
  foundLine = False
  file1 = open(depFile, 'r')
  while True:
    line = file1.readline()
    ll = line.split()
    if not line:
      break
    elif "SUBPACKAGES_DIRS" in line and foundLine == False:
      foundLine = True
    elif foundLine and len(ll) > 2 and '#' not in ll[0]:
      print(ll)
      result.append(ll[1])
  file1.close()
  return result


def findDependenciesFromCmakeFile(cmakeFile, allPackNames):
  re1 = re.compile(r'.*LIB_REQUIRED_PACKAGES\s*([^\n\r)]*)')
  re2 = re.compile(r'.*LIB_REQUIRED_DEP_PACKAGES\s*([^\n\r)]*)')
  re3 = re.compile(r'.*LIB_OPTIONAL_DEP_PACKAGES\s*([^\n\r)]*)')
  reqDeps = []
  optDeps = []

  with open(cmakeFile, 'r') as file:
    fileContent = file.read()

  res1 = re.search(re1, fileContent)
  res2 = re.search(re2, fileContent)
  res3 = re.search(re3, fileContent)
  if res1 != None and res2 != None:
    sys.exit("Something wrong with dep, only one regex should be true")

  if res1 != None:
    depList = res1.group().split()[1:]
    reqDeps = findNeededPackages(depList, allPackNames)

  if res2 != None:
    depList = res2.group().split()[1:]
    result = findNeededPackages(depList, allPackNames)
    reqDeps += result

  if res3 != None:
    depList = res3.group().split()[1:]
    optDeps = findNeededPackages(depList, allPackNames)

  return reqDeps, optDeps


def findLinks(trilPath, packDic):
  # the keys correspond to each package name, get a list of them all
  allPackNames = list(packDic.keys())
  print(allPackNames)

  # loop over each package and find connections
  for packName,v in packDic.items():
    print("\n**************************")
    print(packName)
    print("**************************")
    v["req-deps"] = []
    v["opt-deps"] = []
    v["numsubpack"] = 0

    thisPackDir = trilPath + "/" + v["subdir"]
    if os.path.isdir(thisPackDir):
      topLevelDepFile = thisPackDir + "/cmake/Dependencies.cmake"
      print(topLevelDepFile)
      assert( os.path.isfile(topLevelDepFile) )
      # read dep file
      with open(topLevelDepFile, 'r') as file:
        currDep = file.read()

      # find out if this package has subpackages
      hasSubPack = hasSubpackages(currDep)
      print(hasSubPack)

      if hasSubPack:
        subplist = getSubpackagesDirNames(topLevelDepFile)
        print("subpackages: ", subplist)

        # add to dic # of subpackages
        v["numsubpack"] = len(subplist)

        # loop over each subspace and extract depenedencies for each
        for subpIt in subplist:
          subpDepCmakeFullPath = thisPackDir+"/"+subpIt+"/cmake/Dependencies.cmake"
          print("subpackage cmake file: ", subpDepCmakeFullPath)
          rd, od = findDependenciesFromCmakeFile(subpDepCmakeFullPath, allPackNames)
          v["req-deps"] += rd
          v["opt-deps"] += od

      else:
        rd, od = findDependenciesFromCmakeFile(topLevelDepFile, allPackNames)
        v["req-deps"] += rd
        v["opt-deps"] += od

      # make names unique
      v["req-deps"] = list(set(v["req-deps"]))
      v["opt-deps"] = list(set(v["opt-deps"]))
      print("----- final ----\n")
      print("required : ", v["req-deps"])
      print("optional : ", v["opt-deps"])

    else:
      pass

def readCppLocFromFile(filein):
  mysum = 0
  file1 = open(filein, 'r')
  while True:
    line = file1.readline()
    ll = line.split()
    if not line:
      break
    elif "C++" in line:
      print(ll)
      mysum += int(ll[-1])
  file1.close()
  return mysum

def countLoc(trilPath, packDic):
  allPackNames = list(packDic.keys())
  for packName,v in packDic.items():
    print("\n**************************")
    print(packName)
    print("**************************")

    thisPackDir = trilPath + "/" + v["subdir"]
    if os.path.isdir(thisPackDir):
      args   = ("cloc", thisPackDir)
      logfile = open("tmpcloc.txt", 'w')
      p  = subprocess.Popen(args, stdout=logfile, stderr=logfile)
      p.wait()
      logfile.close()
      v["loc"] = readCppLocFromFile("tmpcloc.txt")
    else:
      v["loc"] = 0

#=========================================
if __name__== "__main__":
#=========================================
  trilPath = "/Users/fnrizzi/Desktop/testTril/Trilinos-trilinos-release-13-0-1"
  packDic = readPackFile()
  countLoc(trilPath, packDic)
  findLinks(trilPath, packDic)

  finalD = {}
  finalD["nodes"] = createNodesList(packDic)
  finalD["links"] = createLinksList(packDic)
  dicToJsonFile(finalD, 'w')
