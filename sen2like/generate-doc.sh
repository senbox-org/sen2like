echo "Generating documentation..."
echo "[Generating apidoc]" > doc-generated.txt
sphinx-apidoc -o docs/source/api -e -P sen2like >> doc-generated.txt 2>&1

#echo -e "\n[Generating autosummary]" >> doc-generated.txt
#PYTHONPATH=. sphinx-autogen docs/source/index.rst >> doc-generated.txt 2>&1

echo -e "\n[Generating html]" >> doc-generated.txt
sphinx-build -b html docs/source docs/output >> doc-generated.txt 2>&1

echo -e "\n[Generating coverage]" >> doc-generated.txt
sphinx-build -b coverage docs/source docs/coverage >> doc-generated.txt 2>&1

echo "See docs/output/index.html for documentation"
echo "See doc-generated.txt for generation report"
sleep 5