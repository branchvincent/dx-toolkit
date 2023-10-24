SELECT `sample_1`.`sample_id` AS `sample_id` FROM `database_gyk3jjj0vgpq2y1y98pj8pgg__create_cohort_geno_database`.`sample` AS `sample_1` WHERE `sample_1`.`sample_id` IN ('sample_1_1', 'sample_1_2', 'sample_1_5') AND `sample_1`.`sample_id` IN (SELECT `assay_cohort_query`.`sample_id` FROM (SELECT `genotype_alt_read_optimized_1`.`sample_id` AS `sample_id` FROM `database_gyk3jjj0vgpq2y1y98pj8pgg__create_cohort_geno_database`.`genotype_alt_read_optimized` AS `genotype_alt_read_optimized_1` WHERE `genotype_alt_read_optimized_1`.`ref_yn` = false AND `genotype_alt_read_optimized_1`.`chr` = '18' AND `genotype_alt_read_optimized_1`.`pos` BETWEEN 46368 AND 48368 AND `genotype_alt_read_optimized_1`.`bin` IN (0) AND `genotype_alt_read_optimized_1`.`type` IN ('hom')) AS `assay_cohort_query`)