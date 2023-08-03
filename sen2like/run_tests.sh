#!/usr/bin/env bash

echo $@

export PYTHONPATH=.:${PYTHONPATH}

[ -d reports ] || mkdir reports

if hash coverage 2> /dev/null; then
    echo **Running tests
    PYTHONPATH=sen2like:aux_data coverage run --branch -m pytest -source=sen2like --log-level=DEBUG --junitxml reports/junit.xml "$@" |& tee reports/tests.report
    out=${PIPESTATUS[0]}
    if [ $out -ne 0 ];
    then
        echo "Error in tests"
        exit $out
    fi
    echo Result file written in $PWD/reports/tests.report
    echo **Running coverage
    coverage xml -o reports/coverage.xml
    out=$?
    if [ $out -ne 0 ];
    then
        echo "Error in coverage xml"
        exit $out
    fi
    echo XML Cobertura report file written in $PWD/reports/coverage.xml
    coverage report -m > reports/coverage.report
    out=$?
    if [ $out -ne 0 ];
    then
        echo "Error in coverage report"
        exit $out
    fi
    echo Report file written in $PWD/reports/coverage.report
    coverage html -d reports/coverage
    out=$?
    if [ $out -ne 0 ];
    then
        echo "Error in coverage html"
        exit $out
    fi
    echo HTML report written in $PWD/reports/coverage.report
    coverage erase
    out=$?
    if [ $out -ne 0 ];
    then
        echo "Error in coverage erase"
        exit $out
    fi
else
    python tests/run_tests.py
fi

if hash pylint 2> /dev/null; then
    # pushd sen2like
    echo **Running pylint code analysis
    PYTHONPATH=sen2like:aux_data pylint --extension-pkg-whitelist=numpy,cv2 --max-line-length=120 -j 8 -r y sen2like/**/*.py aux_data/**/*.py > ../reports/pylint.report
    out=$?
    if [ $out -ne 0 ];
    then
        echo "Error in pylint"
        exit $out
    fi
    echo Result file written in $PWD/reports/pylint.report
    popd
fi

if hash flake8 2> /dev/null; then
    echo **Running flake8
    flake8 --max-line-length=120 --statistics sen2like > reports/flake8.report
    out=$?
    if [ $out -ne 0 ];
    then
        echo "Error in flake"
        exit $out
    fi
    echo Result file written in $PWD/reports/pycodestyle.report
fi

if hash bandit 2> /dev/null; then
    echo **Running code security check
    bandit -r --severity-level high sen2like > reports/bandit.report
    out=$?
    if [ $out -ne 0 ];
    then
        echo "Error in bandit"
        exit $out
    fi
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
