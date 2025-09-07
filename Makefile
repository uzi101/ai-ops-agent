.PHONY: demo test clean

demo:
	bash scripts/demo.sh

test:
	pytest -q

clean:
	rm -rf audit demo/sample_artifacts /tmp/fakesvc.pid /tmp/linops_fillfile
