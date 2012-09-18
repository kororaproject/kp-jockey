#!/bin/bash
if [ -f ../jockey-modaliases/rpmfusion-modules.aliases ]
then
  for x in $(grep kmod-staging ../jockey-modaliases/rpmfusion-modules.aliases |awk '{print $3}' |sort |uniq)
  do
    cp handlers/kmod-staging.py handlers/kmod-staging-$x.py
    sed -i s/STAGING_MODULE/$x/g handlers/kmod-staging-$x.py
  done
else
  echo "I need the rpmfusion-modules.alias file from jockey-modaliases, sorry."
fi
