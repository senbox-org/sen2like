#!/usr/bin/env bash

export PYTHONPATH=.:${PYTHONPATH}

[ -d reports ] || mkdir reports

if hash coverage 2> /dev/null; then
    echo **Running tests
    PYTHONPATH=. coverage run --source=sen2like --branch tests/run_tests.py  > reports/tests.report 2>&1
    echo Result file written in $PWD/reports/tests.report
    echo **Running coverage
    coverage report -m > reports/coverage.report
    coverage html -d reports/coverage
    coverage erase
    echo Result file written in $PWD/reports/coverage.report
    echo Result file written in $PWD/reports/coverage/index.html
else
    python tests/run_tests.py
fi

if hash pylint 2> /dev/null; then
    echo **Running code analysis
    pylint --extension-pkg-whitelist=numpy,cv2 --max-line-length=120 -j 8 -r y sen2like > reports/pylint.report
    echo Result file written in $PWD/reports/pylint.report
fi

if hash flake8 2> /dev/null; then
    flake8 --max-line-length=120 --statistics . > reports/flake8.report
    echo Result file written in $PWD/reports/pycodestyle.report
fi

if hash bandit 2> /dev/null; then
    echo **Running code security check
    bandit -r sen2like > reports/bandit.report
    echo Result file written in $PWD/reports/bandit.report
fi
#
#for i in "$@" ; do
#    # Memory test
#    if [[ ${i} == "--with-memory-profiling" ]]; then
#        if hash mprof 2> /dev/null; then
#            echo **Running memory profiling
#            mprof run python sen2like.py TODO > /dev/null 2>&1
#            mprof plot -o reports/memory_profile.jpg
#            echo Result file written in $PWD/reports/memory_profile.jpg
#            mprof clean
#        fi
#    # CPU test
#    elif [[ ${i} == "--with-cpu-profiling" ]]; then
#        echo **Running cpu profiling
#        python -m cProfile -o reports/profile.dat sen2like.py TODO > /dev/null 2>&1
#        echo "> Run python -m pstats reports/profile.dat for analyzing cpu profile."
#    fi
#done
