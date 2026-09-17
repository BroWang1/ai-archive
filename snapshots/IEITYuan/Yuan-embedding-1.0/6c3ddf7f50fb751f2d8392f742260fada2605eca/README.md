---
model-index:
- name: Yuan-embedding-1.0
  results:
  - dataset:
      config: default
      name: MTEB AFQMC (default)
      revision: None
      split: validation
      type: C-MTEB/AFQMC
    metrics:
    - type: cosine_pearson
      value: 56.398777687800596
    - type: cosine_spearman
      value: 60.2976392017466
    - type: manhattan_pearson
      value: 58.34432755369896
    - type: manhattan_spearman
      value: 59.633715024557176
    - type: euclidean_pearson
      value: 58.33199470250656
    - type: euclidean_spearman
      value: 59.633393360323595
    - type: main_score
      value: 60.2976392017466
    task:
      type: STS
  - dataset:
      config: default
      name: MTEB ATEC (default)
      revision: None
      split: test
      type: C-MTEB/ATEC
    metrics:
    - type: cosine_pearson
      value: 56.418711941754694
    - type: cosine_spearman
      value: 58.49782527525838
    - type: manhattan_pearson
      value: 62.05335398720773
    - type: manhattan_spearman
      value: 58.18176592298454
    - type: euclidean_pearson
      value: 62.06479799788818
    - type: euclidean_spearman
      value: 58.18182671971488
    - type: main_score
      value: 58.49782527525838
    task:
      type: STS
  - dataset:
      config: zh
      name: MTEB AmazonReviewsClassification (zh)
      revision: 1399c76144fd37290681b995c656ef9b2e06e26d
      split: test
      type: mteb/amazon_reviews_multi
    metrics:
    - type: accuracy
      value: 46.656000000000006
    - type: accuracy_stderr
      value: 1.1704631561907444
    - type: f1
      value: 45.75911645865614
    - type: f1_stderr
      value: 1.323301406018355
    - type: main_score
      value: 46.656000000000006
    task:
      type: Classification
  - dataset:
      config: zh
      name: MTEB AmazonReviewsClassification (zh)
      revision: 1399c76144fd37290681b995c656ef9b2e06e26d
      split: validation
      type: mteb/amazon_reviews_multi
    metrics:
    - type: accuracy
      value: 45.84599999999999
    - type: accuracy_stderr
      value: 1.0539468677310073
    - type: f1
      value: 45.03273670979488
    - type: f1_stderr
      value: 1.00417269917164
    - type: main_score
      value: 45.84599999999999
    task:
      type: Classification
  - dataset:
      config: default
      name: MTEB BQ (default)
      revision: None
      split: test
      type: C-MTEB/BQ
    metrics:
    - type: cosine_pearson
      value: 71.33099160181597
    - type: cosine_spearman
      value: 73.06963287952199
    - type: manhattan_pearson
      value: 70.65314181752566
    - type: manhattan_spearman
      value: 72.34604440078336
    - type: euclidean_pearson
      value: 70.67624292501411
    - type: euclidean_spearman
      value: 72.3597691712343
    - type: main_score
      value: 73.06963287952199
    task:
      type: STS
  - dataset:
      config: default
      name: MTEB CLSClusteringP2P (default)
      revision: None
      split: test
      type: C-MTEB/CLSClusteringP2P
    metrics:
    - type: v_measure
      value: 53.79921861868626
    - type: v_measure_std
      value: 2.073016548125077
    - type: main_score
      value: 53.79921861868626
    task:
      type: Clustering
  - dataset:
      config: default
      name: MTEB CLSClusteringS2S (default)
      revision: None
      split: test
      type: C-MTEB/CLSClusteringS2S
    metrics:
    - type: v_measure
      value: 46.22496957569903
    - type: v_measure_std
      value: 1.4660184854965337
    - type: main_score
      value: 46.22496957569903
    task:
      type: Clustering
  - dataset:
      config: default
      name: MTEB CMedQAv1-reranking (default)
      revision: None
      split: test
      type: C-MTEB/CMedQAv1-reranking
    metrics:
    - type: map
      value: 90.00883554654739
    - type: mrr
      value: 92.02547619047618
    - type: main_score
      value: 90.00883554654739
    task:
      type: Reranking
  - dataset:
      config: default
      name: MTEB CMedQAv2-reranking (default)
      revision: None
      split: test
      type: C-MTEB/CMedQAv2-reranking
    metrics:
    - type: map
      value: 92.47561424216632
    - type: mrr
      value: 94.60039682539681
    - type: main_score
      value: 92.47561424216632
    task:
      type: Reranking
  - dataset:
      config: default
      name: MTEB CmedqaRetrieval (default)
      revision: None
      split: dev
      type: C-MTEB/CmedqaRetrieval
    metrics:
    - type: map_at_1
      value: 29.935000000000002
    - type: map_at_10
      value: 44.143
    - type: map_at_100
      value: 45.999
    - type: map_at_1000
      value: 46.084
    - type: map_at_3
      value: 39.445
    - type: map_at_5
      value: 42.218
    - type: mrr_at_1
      value: 44.711
    - type: mrr_at_10
      value: 53.88699999999999
    - type: mrr_at_100
      value: 54.813
    - type: mrr_at_1000
      value: 54.834
    - type: mrr_at_3
      value: 51.1
    - type: mrr_at_5
      value: 52.827
    - type: ndcg_at_1
      value: 44.711
    - type: ndcg_at_10
      value: 51.471999999999994
    - type: ndcg_at_100
      value: 58.362
    - type: ndcg_at_1000
      value: 59.607
    - type: ndcg_at_3
      value: 45.558
    - type: ndcg_at_5
      value: 48.345
    - type: precision_at_1
      value: 44.711
    - type: precision_at_10
      value: 11.1
    - type: precision_at_100
      value: 1.6650000000000003
    - type: precision_at_1000
      value: 0.184
    - type: precision_at_3
      value: 25.306
    - type: precision_at_5
      value: 18.404999999999998
    - type: recall_at_1
      value: 29.935000000000002
    - type: recall_at_10
      value: 63.366
    - type: recall_at_100
      value: 91.375
    - type: recall_at_1000
      value: 99.167
    - type: recall_at_3
      value: 45.888
    - type: recall_at_5
      value: 54.169
    - type: main_score
      value: 51.471999999999994
    task:
      type: Retrieval
  - dataset:
      config: default
      name: MTEB Cmnli (default)
      revision: None
      split: validation
      type: C-MTEB/CMNLI
    metrics:
    - type: cos_sim_accuracy
      value: 80.3968731208659
    - type: cos_sim_accuracy_threshold
      value: 86.61384582519531
    - type: cos_sim_ap
      value: 88.21894124132636
    - type: cos_sim_f1
      value: 81.67308750687947
    - type: cos_sim_f1_threshold
      value: 86.04017496109009
    - type: cos_sim_precision
      value: 77.1630615640599
    - type: cos_sim_recall
      value: 86.7430441898527
    - type: dot_accuracy
      value: 67.7931449188214
    - type: dot_accuracy_threshold
      value: 92027.47802734375
    - type: dot_ap
      value: 75.73048600318765
    - type: dot_f1
      value: 71.64554512914772
    - type: dot_f1_threshold
      value: 83535.70556640625
    - type: dot_precision
      value: 61.1056105610561
    - type: dot_recall
      value: 86.57937806873977
    - type: euclidean_accuracy
      value: 78.52074564040889
    - type: euclidean_accuracy_threshold
      value: 1688.486671447754
    - type: euclidean_ap
      value: 86.40643721988414
    - type: euclidean_f1
      value: 79.97822536744692
    - type: euclidean_f1_threshold
      value: 1748.1914520263672
    - type: euclidean_precision
      value: 74.83700081499592
    - type: euclidean_recall
      value: 85.87795183539865
    - type: manhattan_accuracy
      value: 78.59290438965725
    - type: manhattan_accuracy_threshold
      value: 57066.162109375
    - type: manhattan_ap
      value: 86.38300352696045
    - type: manhattan_f1
      value: 79.84587391630097
    - type: manhattan_f1_threshold
      value: 59686.376953125
    - type: manhattan_precision
      value: 73.62810896170548
    - type: manhattan_recall
      value: 87.21066167874679
    - type: max_accuracy
      value: 80.3968731208659
    - type: max_ap
      value: 88.21894124132636
    - type: max_f1
      value: 81.67308750687947
    task:
      type: PairClassification
  - dataset:
      config: default
      name: MTEB CovidRetrieval (default)
      revision: None
      split: dev
      type: C-MTEB/CovidRetrieval
    metrics:
    - type: map_at_1
      value: 85.485
    - type: map_at_10
      value: 91.135
    - type: map_at_100
      value: 91.16199999999999
    - type: map_at_1000
      value: 91.16300000000001
    - type: map_at_3
      value: 90.499
    - type: map_at_5
      value: 90.91
    - type: mrr_at_1
      value: 85.88
    - type: mrr_at_10
      value: 91.133
    - type: mrr_at_100
      value: 91.16
    - type: mrr_at_1000
      value: 91.161
    - type: mrr_at_3
      value: 90.551
    - type: mrr_at_5
      value: 90.904
    - type: ndcg_at_1
      value: 85.88
    - type: ndcg_at_10
      value: 93.163
    - type: ndcg_at_100
      value: 93.282
    - type: ndcg_at_1000
      value: 93.309
    - type: ndcg_at_3
      value: 91.943
    - type: ndcg_at_5
      value: 92.637
    - type: precision_at_1
      value: 85.88
    - type: precision_at_10
      value: 10.032
    - type: precision_at_100
      value: 1.008
    - type: precision_at_1000
      value: 0.101
    - type: precision_at_3
      value: 32.315
    - type: precision_at_5
      value: 19.747
    - type: recall_at_1
      value: 85.485
    - type: recall_at_10
      value: 99.262
    - type: recall_at_100
      value: 99.789
    - type: recall_at_1000
      value: 100.0
    - type: recall_at_3
      value: 95.96900000000001
    - type: recall_at_5
      value: 97.682
    - type: main_score
      value: 93.163
    task:
      type: Retrieval
  - dataset:
      config: default
      name: MTEB DuRetrieval (default)
      revision: None
      split: dev
      type: C-MTEB/DuRetrieval
    metrics:
    - type: map_at_1
      value: 27.29
    - type: map_at_10
      value: 82.832
    - type: map_at_100
      value: 85.482
    - type: map_at_1000
      value: 85.52
    - type: map_at_3
      value: 57.964000000000006
    - type: map_at_5
      value: 72.962
    - type: mrr_at_1
      value: 92.35
    - type: mrr_at_10
      value: 94.77499999999999
    - type: mrr_at_100
      value: 94.825
    - type: mrr_at_1000
      value: 94.827
    - type: mrr_at_3
      value: 94.50800000000001
    - type: mrr_at_5
      value: 94.688
    - type: ndcg_at_1
      value: 92.35
    - type: ndcg_at_10
      value: 89.432
    - type: ndcg_at_100
      value: 91.813
    - type: ndcg_at_1000
      value: 92.12
    - type: ndcg_at_3
      value: 88.804
    - type: ndcg_at_5
      value: 87.681
    - type: precision_at_1
      value: 92.35
    - type: precision_at_10
      value: 42.32
    - type: precision_at_100
      value: 4.812
    - type: precision_at_1000
      value: 0.48900000000000005
    - type: precision_at_3
      value: 79.367
    - type: precision_at_5
      value: 66.86999999999999
    - type: recall_at_1
      value: 27.29
    - type: recall_at_10
      value: 90.093
    - type: recall_at_100
      value: 97.916
    - type: recall_at_1000
      value: 99.40299999999999
    - type: recall_at_3
      value: 59.816
    - type: recall_at_5
      value: 76.889
    - type: main_score
      value: 89.432
    task:
      type: Retrieval
  - dataset:
      config: default
      name: MTEB EcomRetrieval (default)
      revision: None
      split: dev
      type: C-MTEB/EcomRetrieval
    metrics:
    - type: map_at_1
      value: 55.2
    - type: map_at_10
      value: 65.767
    - type: map_at_100
      value: 66.208
    - type: map_at_1000
      value: 66.219
    - type: map_at_3
      value: 63.1
    - type: map_at_5
      value: 64.865
    - type: mrr_at_1
      value: 55.2
    - type: mrr_at_10
      value: 65.767
    - type: mrr_at_100
      value: 66.208
    - type: mrr_at_1000
      value: 66.219
    - type: mrr_at_3
      value: 63.1
    - type: mrr_at_5
      value: 64.865
    - type: ndcg_at_1
      value: 55.2
    - type: ndcg_at_10
      value: 70.875
    - type: ndcg_at_100
      value: 72.931
    - type: ndcg_at_1000
      value: 73.2
    - type: ndcg_at_3
      value: 65.526
    - type: ndcg_at_5
      value: 68.681
    - type: precision_at_1
      value: 55.2
    - type: precision_at_10
      value: 8.690000000000001
    - type: precision_at_100
      value: 0.963
    - type: precision_at_1000
      value: 0.098
    - type: precision_at_3
      value: 24.166999999999998
    - type: precision_at_5
      value: 16.02
    - type: recall_at_1
      value: 55.2
    - type: recall_at_10
      value: 86.9
    - type: recall_at_100
      value: 96.3
    - type: recall_at_1000
      value: 98.4
    - type: recall_at_3
      value: 72.5
    - type: recall_at_5
      value: 80.10000000000001
    - type: main_score
      value: 70.875
    task:
      type: Retrieval
  - dataset:
      config: default
      name: MTEB IFlyTek (default)
      revision: None
      split: validation
      type: C-MTEB/IFlyTek-classification
    metrics:
    - type: accuracy
      value: 46.95652173913043
    - type: accuracy_stderr
      value: 0.8816372193041417
    - type: f1
      value: 38.870262239396496
    - type: f1_stderr
      value: 1.1248427890133785
    - type: main_score
      value: 46.95652173913043
    task:
      type: Classification
  - dataset:
      config: default
      name: MTEB JDReview (default)
      revision: None
      split: test
      type: C-MTEB/JDReview-classification
    metrics:
    - type: accuracy
      value: 87.18574108818011
    - type: accuracy_stderr
      value: 1.828763099528331
    - type: ap
      value: 56.516251295719414
    - type: ap_stderr
      value: 3.3789918068717895
    - type: f1
      value: 82.04209146803106
    - type: f1_stderr
      value: 2.005027201503808
    - type: main_score
      value: 87.18574108818011
    task:
      type: Classification
  - dataset:
      config: default
      name: MTEB LCQMC (default)
      revision: None
      split: test
      type: C-MTEB/LCQMC
    metrics:
    - type: cosine_pearson
      value: 72.67112275922743
    - type: cosine_spearman
      value: 78.44376213964316
    - type: manhattan_pearson
      value: 77.51766838932976
    - type: manhattan_spearman
      value: 78.02885255071602
    - type: euclidean_pearson
      value: 77.5292348074114
    - type: euclidean_spearman
      value: 78.04277103380235
    - type: main_score
      value: 78.44376213964316
    task:
      type: STS
  - dataset:
      config: default
      name: MTEB MMarcoReranking (default)
      revision: None
      split: dev
      type: C-MTEB/Mmarco-reranking
    metrics:
    - type: map
      value: 37.021133625346174
    - type: mrr
      value: 35.81428571428572
    - type: main_score
      value: 37.021133625346174
    task:
      type: Reranking
  - dataset:
      config: default
      name: MTEB MMarcoRetrieval (default)
      revision: None
      split: dev
      type: C-MTEB/MMarcoRetrieval
    metrics:
    - type: map_at_1
      value: 69.624
    - type: map_at_10
      value: 78.764
    - type: map_at_100
      value: 79.038
    - type: map_at_1000
      value: 79.042
    - type: map_at_3
      value: 76.846
    - type: map_at_5
      value: 78.106
    - type: mrr_at_1
      value: 71.905
    - type: mrr_at_10
      value: 79.268
    - type: mrr_at_100
      value: 79.508
    - type: mrr_at_1000
      value: 79.512
    - type: mrr_at_3
      value: 77.60000000000001
    - type: mrr_at_5
      value: 78.701
    - type: ndcg_at_1
      value: 71.905
    - type: ndcg_at_10
      value: 82.414
    - type: ndcg_at_100
      value: 83.59
    - type: ndcg_at_1000
      value: 83.708
    - type: ndcg_at_3
      value: 78.803
    - type: ndcg_at_5
      value: 80.94
    - type: precision_at_1
      value: 71.905
    - type: precision_at_10
      value: 9.901
    - type: precision_at_100
      value: 1.048
    - type: precision_at_1000
      value: 0.106
    - type: precision_at_3
      value: 29.479
    - type: precision_at_5
      value: 18.828
    - type: recall_at_1
      value: 69.624
    - type: recall_at_10
      value: 93.149
    - type: recall_at_100
      value: 98.367
    - type: recall_at_1000
      value: 99.29299999999999
    - type: recall_at_3
      value: 83.67599999999999
    - type: recall_at_5
      value: 88.752
    - type: main_score
      value: 82.414
    task:
      type: Retrieval
  - dataset:
      config: zh-CN
      name: MTEB MassiveIntentClassification (zh-CN)
      revision: 31efe3c427b0bae9c22cbb560b8f15491cc6bed7
      split: test
      type: mteb/amazon_massive_intent
    metrics:
    - type: accuracy
      value: 77.36045729657029
    - type: accuracy_stderr
      value: 0.8944498935111289
    - type: f1
      value: 73.73485209304225
    - type: f1_stderr
      value: 0.8615191738484445
    - type: main_score
      value: 77.36045729657029
    task:
      type: Classification
  - dataset:
      config: zh-CN
      name: MTEB MassiveIntentClassification (zh-CN)
      revision: 31efe3c427b0bae9c22cbb560b8f15491cc6bed7
      split: validation
      type: mteb/amazon_massive_intent
    metrics:
    - type: accuracy
      value: 78.16035415641909
    - type: accuracy_stderr
      value: 0.7514724220154535
    - type: f1
      value: 75.32402452596266
    - type: f1_stderr
      value: 0.5969737694527888
    - type: main_score
      value: 78.16035415641909
    task:
      type: Classification
  - dataset:
      config: zh-CN
      name: MTEB MassiveScenarioClassification (zh-CN)
      revision: 7d571f92784cd94a019292a1f45445077d0ef634
      split: test
      type: mteb/amazon_massive_scenario
    metrics:
    - type: accuracy
      value: 83.31203765971755
    - type: accuracy_stderr
      value: 1.1063564012537301
    - type: f1
      value: 82.81655735858999
    - type: f1_stderr
      value: 0.9643568609098954
    - type: main_score
      value: 83.31203765971755
    task:
      type: Classification
  - dataset:
      config: zh-CN
      name: MTEB MassiveScenarioClassification (zh-CN)
      revision: 7d571f92784cd94a019292a1f45445077d0ef634
      split: validation
      type: mteb/amazon_massive_scenario
    metrics:
    - type: accuracy
      value: 83.11362518445647
    - type: accuracy_stderr
      value: 1.252141689154366
    - type: f1
      value: 82.56555569957769
    - type: f1_stderr
      value: 0.858322314243248
    - type: main_score
      value: 83.11362518445647
    task:
      type: Classification
  - dataset:
      config: default
      name: MTEB MedicalRetrieval (default)
      revision: None
      split: dev
      type: C-MTEB/MedicalRetrieval
    metrics:
    - type: map_at_1
      value: 63.1
    - type: map_at_10
      value: 70.816
    - type: map_at_100
      value: 71.368
    - type: map_at_1000
      value: 71.379
    - type: map_at_3
      value: 69.033
    - type: map_at_5
      value: 70.028
    - type: mrr_at_1
      value: 63.4
    - type: mrr_at_10
      value: 70.98400000000001
    - type: mrr_at_100
      value: 71.538
    - type: mrr_at_1000
      value: 71.548
    - type: mrr_at_3
      value: 69.19999999999999
    - type: mrr_at_5
      value: 70.195
    - type: ndcg_at_1
      value: 63.1
    - type: ndcg_at_10
      value: 74.665
    - type: ndcg_at_100
      value: 77.16199999999999
    - type: ndcg_at_1000
      value: 77.408
    - type: ndcg_at_3
      value: 70.952
    - type: ndcg_at_5
      value: 72.776
    - type: precision_at_1
      value: 63.1
    - type: precision_at_10
      value: 8.68
    - type: precision_at_100
      value: 0.9809999999999999
    - type: precision_at_1000
      value: 0.1
    - type: precision_at_3
      value: 25.5
    - type: precision_at_5
      value: 16.2
    - type: recall_at_1
      value: 63.1
    - type: recall_at_10
      value: 86.8
    - type: recall_at_100
      value: 98.1
    - type: recall_at_1000
      value: 100.0
    - type: recall_at_3
      value: 76.5
    - type: recall_at_5
      value: 81.0
    - type: main_score
      value: 74.665
    task:
      type: Retrieval
  - dataset:
      config: default
      name: MTEB MultilingualSentiment (default)
      revision: None
      split: validation
      type: C-MTEB/MultilingualSentiment-classification
    metrics:
    - type: accuracy
      value: 75.98
    - type: accuracy_stderr
      value: 0.8634813257969153
    - type: f1
      value: 75.98312901227456
    - type: f1_stderr
      value: 0.9813231777702479
    - type: main_score
      value: 75.98
    task:
      type: Classification
  - dataset:
      config: default
      name: MTEB Ocnli (default)
      revision: None
      split: validation
      type: C-MTEB/OCNLI
    metrics:
    - type: cos_sim_accuracy
      value: 80.02165674066053
    - type: cos_sim_accuracy_threshold
      value: 84.70024466514587
    - type: cos_sim_ap
      value: 84.5948682253982
    - type: cos_sim_f1
      value: 80.84291187739463
    - type: cos_sim_f1_threshold
      value: 82.62853622436523
    - type: cos_sim_precision
      value: 73.97020157756354
    - type: cos_sim_recall
      value: 89.1235480464625
    - type: dot_accuracy
      value: 71.52138603140227
    - type: dot_accuracy_threshold
      value: 84206.94580078125
    - type: dot_ap
      value: 77.69986172282461
    - type: dot_f1
      value: 74.76467951591216
    - type: dot_f1_threshold
      value: 78842.08984375
    - type: dot_precision
      value: 64.95327102803739
    - type: dot_recall
      value: 88.0675818373812
    - type: euclidean_accuracy
      value: 76.01515971846237
    - type: euclidean_accuracy_threshold
      value: 1818.9674377441406
    - type: euclidean_ap
      value: 80.84369691331835
    - type: euclidean_f1
      value: 78.08988764044943
    - type: euclidean_f1_threshold
      value: 1922.1363067626953
    - type: euclidean_precision
      value: 70.14297729184187
    - type: euclidean_recall
      value: 88.0675818373812
    - type: manhattan_accuracy
      value: 76.12344342176502
    - type: manhattan_accuracy_threshold
      value: 61934.478759765625
    - type: manhattan_ap
      value: 80.8051823205177
    - type: manhattan_f1
      value: 78.21596244131456
    - type: manhattan_f1_threshold
      value: 64840.447998046875
    - type: manhattan_precision
      value: 70.41420118343196
    - type: manhattan_recall
      value: 87.96198521647307
    - type: max_accuracy
      value: 80.02165674066053
    - type: max_ap
      value: 84.5948682253982
    - type: max_f1
      value: 80.84291187739463
    task:
      type: PairClassification
  - dataset:
      config: default
      name: MTEB OnlineShopping (default)
      revision: None
      split: test
      type: C-MTEB/OnlineShopping-classification
    metrics:
    - type: accuracy
      value: 93.63
    - type: accuracy_stderr
      value: 0.7253275122315392
    - type: ap
      value: 91.66092551327398
    - type: ap_stderr
      value: 0.9661774073521741
    - type: f1
      value: 93.61696896914624
    - type: f1_stderr
      value: 0.7232416235078093
    - type: main_score
      value: 93.63
    task:
      type: Classification
  - dataset:
      config: default
      name: MTEB PAWSX (default)
      revision: None
      split: test
      type: C-MTEB/PAWSX
    metrics:
    - type: cosine_pearson
      value: 27.420084312732477
    - type: cosine_spearman
      value: 36.615019324915316
    - type: manhattan_pearson
      value: 35.38814491527626
    - type: manhattan_spearman
      value: 35.989020517540105
    - type: euclidean_pearson
      value: 35.322828019800475
    - type: euclidean_spearman
      value: 35.93118948093057
    - type: main_score
      value: 36.615019324915316
    task:
      type: STS
  - dataset:
      config: default
      name: MTEB QBQTC (default)
      revision: None
      split: test
      type: C-MTEB/QBQTC
    metrics:
    - type: cosine_pearson
      value: 36.51779732355864
    - type: cosine_spearman
      value: 38.35615142712016
    - type: manhattan_pearson
      value: 31.00096996824444
    - type: manhattan_spearman
      value: 35.22782463612116
    - type: euclidean_pearson
      value: 31.04604995563808
    - type: euclidean_spearman
      value: 35.271420992011485
    - type: main_score
      value: 38.35615142712016
    task:
      type: STS
  - dataset:
      config: zh
      name: MTEB STS22 (zh)
      revision: 6d1ba47164174a496b7fa5d3569dae26a6813b80
      split: test
      type: mteb/sts22-crosslingual-sts
    metrics:
    - type: cosine_pearson
      value: 60.76376961662733
    - type: cosine_spearman
      value: 65.93112312064913
    - type: manhattan_pearson
      value: 60.18998639945854
    - type: manhattan_spearman
      value: 64.37697612695015
    - type: euclidean_pearson
      value: 60.287759656277814
    - type: euclidean_spearman
      value: 64.37685757691955
    - type: main_score
      value: 65.93112312064913
    task:
      type: STS
  - dataset:
      config: default
      name: MTEB STSB (default)
      revision: None
      split: test
      type: C-MTEB/STSB
    metrics:
    - type: cosine_pearson
      value: 79.6320389543562
    - type: cosine_spearman
      value: 81.9230633773663
    - type: manhattan_pearson
      value: 80.20746913195181
    - type: manhattan_spearman
      value: 80.43150657863002
    - type: euclidean_pearson
      value: 80.1796408157508
    - type: euclidean_spearman
      value: 80.42930201788549
    - type: main_score
      value: 81.9230633773663
    task:
      type: STS
  - dataset:
      config: default
      name: MTEB T2Reranking (default)
      revision: None
      split: dev
      type: C-MTEB/T2Reranking
    metrics:
    - type: map
      value: 66.67836204644267
    - type: mrr
      value: 76.1707222383424
    - type: main_score
      value: 66.67836204644267
    task:
      type: Reranking
  - dataset:
      config: default
      name: MTEB T2Retrieval (default)
      revision: None
      split: dev
      type: C-MTEB/T2Retrieval
    metrics:
    - type: map_at_1
      value: 28.015
    - type: map_at_10
      value: 78.281
    - type: map_at_100
      value: 81.89699999999999
    - type: map_at_1000
      value: 81.95599999999999
    - type: map_at_3
      value: 55.117000000000004
    - type: map_at_5
      value: 67.647
    - type: mrr_at_1
      value: 90.496
    - type: mrr_at_10
      value: 93.132
    - type: mrr_at_100
      value: 93.207
    - type: mrr_at_1000
      value: 93.209
    - type: mrr_at_3
      value: 92.714
    - type: mrr_at_5
      value: 93.0
    - type: ndcg_at_1
      value: 90.496
    - type: ndcg_at_10
      value: 85.71600000000001
    - type: ndcg_at_100
      value: 89.164
    - type: ndcg_at_1000
      value: 89.71000000000001
    - type: ndcg_at_3
      value: 86.876
    - type: ndcg_at_5
      value: 85.607
    - type: precision_at_1
      value: 90.496
    - type: precision_at_10
      value: 42.398
    - type: precision_at_100
      value: 5.031
    - type: precision_at_1000
      value: 0.516
    - type: precision_at_3
      value: 75.729
    - type: precision_at_5
      value: 63.522
    - type: recall_at_1
      value: 28.015
    - type: recall_at_10
      value: 84.83000000000001
    - type: recall_at_100
      value: 95.964
    - type: recall_at_1000
      value: 98.67399999999999
    - type: recall_at_3
      value: 56.898
    - type: recall_at_5
      value: 71.163
    - type: main_score
      value: 85.71600000000001
    task:
      type: Retrieval
  - dataset:
      config: default
      name: MTEB TNews (default)
      revision: None
      split: validation
      type: C-MTEB/TNews-classification
    metrics:
    - type: accuracy
      value: 51.702999999999996
    - type: accuracy_stderr
      value: 0.8183526134863877
    - type: f1
      value: 50.35330734766769
    - type: f1_stderr
      value: 0.740275098366631
    - type: main_score
      value: 51.702999999999996
    task:
      type: Classification
  - dataset:
      config: default
      name: MTEB ThuNewsClusteringP2P (default)
      revision: None
      split: test
      type: C-MTEB/ThuNewsClusteringP2P
    metrics:
    - type: v_measure
      value: 72.78709391223538
    - type: v_measure_std
      value: 1.5927130767880417
    - type: main_score
      value: 72.78709391223538
    task:
      type: Clustering
  - dataset:
      config: default
      name: MTEB ThuNewsClusteringS2S (default)
      revision: None
      split: test
      type: C-MTEB/ThuNewsClusteringS2S
    metrics:
    - type: v_measure
      value: 66.80392174700211
    - type: v_measure_std
      value: 1.845756306548485
    - type: main_score
      value: 66.80392174700211
    task:
      type: Clustering
  - dataset:
      config: default
      name: MTEB VideoRetrieval (default)
      revision: None
      split: dev
      type: C-MTEB/VideoRetrieval
    metrics:
    - type: map_at_1
      value: 65.5
    - type: map_at_10
      value: 75.38
    - type: map_at_100
      value: 75.756
    - type: map_at_1000
      value: 75.75800000000001
    - type: map_at_3
      value: 73.8
    - type: map_at_5
      value: 74.895
    - type: mrr_at_1
      value: 65.5
    - type: mrr_at_10
      value: 75.38
    - type: mrr_at_100
      value: 75.756
    - type: mrr_at_1000
      value: 75.75800000000001
    - type: mrr_at_3
      value: 73.8
    - type: mrr_at_5
      value: 74.895
    - type: ndcg_at_1
      value: 65.5
    - type: ndcg_at_10
      value: 79.572
    - type: ndcg_at_100
      value: 81.17699999999999
    - type: ndcg_at_1000
      value: 81.227
    - type: ndcg_at_3
      value: 76.44999999999999
    - type: ndcg_at_5
      value: 78.404
    - type: precision_at_1
      value: 65.5
    - type: precision_at_10
      value: 9.24
    - type: precision_at_100
      value: 0.9939999999999999
    - type: precision_at_1000
      value: 0.1
    - type: precision_at_3
      value: 28.033
    - type: precision_at_5
      value: 17.76
    - type: recall_at_1
      value: 65.5
    - type: recall_at_10
      value: 92.4
    - type: recall_at_100
      value: 99.4
    - type: recall_at_1000
      value: 99.8
    - type: recall_at_3
      value: 84.1
    - type: recall_at_5
      value: 88.8
    - type: main_score
      value: 79.572
    task:
      type: Retrieval
  - dataset:
      config: default
      name: MTEB Waimai (default)
      revision: None
      split: test
      type: C-MTEB/waimai-classification
    metrics:
    - type: accuracy
      value: 88.70000000000002
    - type: accuracy_stderr
      value: 1.1713240371477067
    - type: ap
      value: 73.95357766936226
    - type: ap_stderr
      value: 2.3258932220157638
    - type: f1
      value: 87.27541455081986
    - type: f1_stderr
      value: 1.185968184225313
    - type: main_score
      value: 88.70000000000002
    task:
      type: Classification
tags:
- mteb
---
## Yuan-embedding-1.0

Yuan-embedding-1.0 是专门为中文文本检索任务设计的嵌入模型。
在xiaobu模型结构(bert-large结构)基础上, 采用全新的数据集构建、生成与清洗方法, 结合二阶段微调实现Retrieval任务的精度领先(Hugging Face C-MTEB榜单 [1])。
其中, 正负例样本采用源2.0-M32(Yuan2.0-M32 [2])大模型进行生成。主要工作如下：

- 在Hard negative sampling中，使用Rerank模型(bge-reranker-large [3])进行数据排序筛选
  
- 通过(Yuan2.0-M32大模型)迭代生成新query、corpus
  
- 采用MRL方法进行模型微调训练
  

## Usage

```bash
pip install -U sentence-transformers==3.1.1
```

使用示例：

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("IEIYuan/Yuan-embedding-1.0")
sentences = [
    "这是一个样例-1",
    "这是一个样例-2",
]
embeddings = model.encode(sentences)
similarities = model.similarity(embeddings, embeddings)
print(similarities)
```

## Reference

1. https://huggingface.co/spaces/mteb/leaderboard
2. https://huggingface.co/IEITYuan/Yuan2-M32
3. https://huggingface.co/BAAI/bge-reranker-large