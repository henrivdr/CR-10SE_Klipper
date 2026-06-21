 
cp $1.config .config & make V=1 CROSS_PREFIX=arm-none-eabi-
cp out/$1*.bin fw/F003/
