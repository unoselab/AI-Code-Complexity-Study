

conda env export > env_dev/cursorstudy-full.yml
grep -v "^prefix:" env_dev/cursorstudy-full.yml > env_dev/cursorstudy-full-no-prefix.yml

conda list --explicit > env_dev/cursorstudy-explicit-linux-64.txt
conda list > env_dev/conda-list.txt

pip freeze > env_dev/pip-freeze.txt

Rscript -e "ip <- as.data.frame(installed.packages()[, c('Package','Version','LibPath')]); write.csv(ip, 'env_dev/r-installed-packages.csv', row.names=FALSE)"
Rscript -e "sink('env_dev/r-session-info.txt'); sessionInfo(); sink()"

date > env_dev/export-date.txt
uname -a > env_dev/system-uname.txt
