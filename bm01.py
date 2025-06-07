import sys
import pandas as pd

from ai_benchmark import AIBenchmark

# benchmark = AIBenchmark(verbose_level=3)
# results = benchmark.run()
print(f"Python {sys.version}")

test_ids = [
    "3",
    "5",
]

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
