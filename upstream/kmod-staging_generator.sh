#!/bin/bash
modalias="../../jockey-modaliases/upstream/rpmfusion-modules.aliases"
if [ -f "$modalias" ]
then
  rm -f data/handlers/kmod-staging-*
  for x in $(grep kmod-staging "$modalias" |awk '{print $3}' |sort |uniq)
  do
    cp data/handlers/kmod-staging.py data/handlers/kmod-staging-$x.py
    sed -i s/STAGING_MODULE/$x/g data/handlers/kmod-staging-$x.py
  done
else
  echo "I need the rpmfusion-modules.alias file from jockey-modaliases, sorry."
fi
