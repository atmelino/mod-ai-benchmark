import sys
import pandas as pd
# for Kaggle:
# sys.path.append('./mod-ai-benchmark')

from ai_benchmark import AIBenchmark

# benchmark = AIBenchmark(verbose_level=3)
# results = benchmark.run()
print(f"Python {sys.version}")

test_ids = ["1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16","17","19",]
test_ids = ["3",]

testInfo, public_results, resultCollector = AIBenchmark().run(test_ids=test_ids)
# print(testInfo)
print("*  CPU: %s", testInfo.cpu_model)

# print(public_results)
# print(resultCollector)
print(resultCollector[0])
# print(resultCollector.len())

# for r in resultCollector:
#     print(r)

df=pd.DataFrame(resultCollector)
print(df)
df=df.transpose()
print(df)

df.to_csv('output.csv', index=False)

    # if std > 1 and mean > 100:
    #         mean=round(mean)
    #         round=round(std)
