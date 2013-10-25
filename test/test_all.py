"""
30 Oct 2012

unittest for pytadbit functions
"""

import unittest
from pytadbit                        import Chromosome, load_chromosome
from pytadbit                        import tadbit, batch_tadbit
from pytadbit.tad_clustering.tad_cmo import optimal_cmo
from pytadbit.parsers.hic_parser     import __check_hic as check_hic
from pytadbit.imp.structuralmodels   import load_structuralmodels
from os                              import system, path, chdir
from warnings                        import warn
from distutils.spawn                 import find_executable

PATH = path.abspath(path.split(path.realpath(__file__))[0])

class TestTadbit(unittest.TestCase):
    """
    test main tadbit functions
    """
   
    def test_01_tadbit(self):

        print 'PYTHON SIDE'
        print '-----------'

        global exp1, exp2, exp3, exp4
        exp1 = tadbit(PATH + '/40Kb/chrT/chrT_A.tsv', max_tad_size="auto",
                      verbose=False, no_heuristic=False, n_cpus='max')
        exp2 = tadbit(PATH + '/20Kb/chrT/chrT_B.tsv', max_tad_size="auto",
                      verbose=False, no_heuristic=False, n_cpus='max')
        exp3 = tadbit(PATH + '/20Kb/chrT/chrT_C.tsv', max_tad_size="auto",
                      verbose=False, no_heuristic=False, n_cpus='max')
        exp4 = tadbit(PATH + '/20Kb/chrT/chrT_D.tsv', max_tad_size="auto",
                      n_cpus='max',
                      verbose=False, no_heuristic=False, get_weights=True)

        breaks = [0, 4, 10, 15, 23, 29, 38, 45]
        scores = [7.0, 7.0, 5.0, 7.0, 4.0, 6.0, 8.0, None]
        self.assertEqual(exp1['start'], breaks)
        self.assertEqual(exp1['score'], scores)


    def test_02_batch_tadbit(self):
        global batch_exp
        batch_exp = batch_tadbit('20Kb/chrT/', max_tad_size=20, verbose=False,
                                 no_heuristic=True)
        breaks = [0, 4, 9, 15, 20, 29, 36, 44, 50, 62, 67, 76, 90, 95]
        scores = [4.0, 7.0, 4.0, 8.0, 4.0, 4.0, 7.0, 7.0, 10.0, 10.0, 9.0, 8.0,
                  7.0, None]
        self.assertEqual(batch_exp['start'], breaks)
        self.assertEqual(batch_exp['score'], scores)


    def test_03_tad_multi_aligner(self):

        test_chr = Chromosome(name='Test Chromosome', centromere_search=True,
                              experiment_tads=[exp1, exp2, exp3, exp4],
                              experiment_hic_data=[PATH + '/40Kb/chrT/chrT_A.tsv',
                                                   PATH + '/20Kb/chrT/chrT_B.tsv',
                                                   PATH + '/20Kb/chrT/chrT_C.tsv',
                                                   PATH + '/20Kb/chrT/chrT_D.tsv'],
                              experiment_names=['exp1', 'exp2', 'exp3', 'exp4'],
                              experiment_resolutions=[40000,20000,20000,20000],
                              silent=True)
        for exp in test_chr.experiments:
            exp.normalize_hic(method='visibility', silent=True)

        test_chr.align_experiments(verbose=False, randomize=False,
                                   method='global')
        score1, pval1 = test_chr.align_experiments(verbose=False,method='global',
                                                   randomize=True)
        _, pval2 = test_chr.align_experiments(verbose=False, randomize=True,
                                              rnd_method='shuffle')
        self.assertEqual(round(-26.095, 3), round(score1, 3))
        self.assertEqual(round(0.001, 1), round(pval1, 1))
        self.assertTrue(abs(0.175 - pval2) < 0.2)

                              
    def test_04_chromosome_batch(self):
        test_chr = Chromosome(name='Test Chromosome',
                              experiment_resolutions=[20000]*3,
                              experiment_hic_data=[PATH + '/20Kb/chrT/chrT_A.tsv',
                                                   PATH + '/20Kb/chrT/chrT_D.tsv',
                                                   PATH + '/20Kb/chrT/chrT_C.tsv'],
                              experiment_names=['exp1', 'exp2', 'exp3'])
        test_chr.find_tad(['exp1', 'exp2', 'exp3'], batch_mode=True,
                          verbose=False)
        tads = test_chr.get_experiment('batch_exp1_exp2_exp3').tads
        found = [tads[t]['end'] for t in tads if tads[t]['score'] > 0]
        self.assertEqual([3.0, 8.0, 16.0, 21.0, 28.0, 35.0, 43.0,
                          49.0, 61.0, 66.0, 75.0, 89.0, 94.0, 99.0], found)


    def test_05_save_load(self):
        test_chr1 = Chromosome(name='Test Chromosome',
                              experiment_tads=[exp1, exp2],
                              experiment_names=['exp1', 'exp2'],
                              experiment_resolutions=[20000,20000])
        test_chr1.save_chromosome('lolo', force=True)
        test_chr2 = load_chromosome('lolo')
        system('rm -f lolo')
        system('rm -f lolo_hic')
        self.assertEqual(str(test_chr1.__dict__), str(test_chr2.__dict__))


    def test_06_tad_clustering(self):
        test_chr = Chromosome(name='Test Chromosome',
                              experiment_tads=[exp4],
                              experiment_names=['exp1'],
                              experiment_hic_data=[PATH + '/20Kb/chrT/chrT_D.tsv'],
                              experiment_resolutions=[20000,20000])
        all_tads = []
        for _, tad in test_chr.iter_tads('exp1'):
            all_tads.append(tad)
        align1, align2, _ = optimal_cmo(all_tads[7], all_tads[10], 7,
                                        method='score')
        self.assertEqual(align1, [0, 1, '-', 2, 3, '-', 4, 5, 6, 7, 8, 9, 10])
        self.assertEqual(align2,[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
        

    def test_07_forbidden_regions(self):
        test_chr = Chromosome(name='Test Chromosome', max_tad_size=260000,
                              centromere_search=True,)
        test_chr.add_experiment('exp1', 20000, tad_def=exp4,
                                hic_data=PATH + '/20Kb/chrT/chrT_D.tsv')
        brks = [2.0, 7.0, 12.0, 18.0, 38.0, 43.0, 49.0,
                61.0, 66.0, 75.0, 89.0, 94.0, 99.0]
        tads = test_chr.experiments['exp1'].tads
        found = [tads[t]['end'] for t in tads if tads[t]['score'] > 0]
        self.assertEqual(brks, found)
        items1 = test_chr.forbidden.keys(), test_chr.forbidden.values()
        test_chr.add_experiment('exp2', 20000, tad_def=exp3,
                                hic_data=PATH + '/20Kb/chrT/chrT_C.tsv')
        items2 = test_chr.forbidden.keys(), test_chr.forbidden.values()
        know1 = ([32, 33, 34, 38, 39, 19, 20, 21, 22,
                  23, 24, 25, 26, 27, 28, 29, 30, 31],
                 [None, None, None, 'Centromere', 'Centromere',
                  None, None, None, None, None, None, None,
                  None, None, None, None, None, None])
        know2 = ([38], ['Centromere'])
        self.assertEqual(items1, know1)
        self.assertEqual(items2, know2)


    def test_08_changing_resolution(self):
        test_chr = Chromosome(name='Test Chromosome', max_tad_size=260000)
        test_chr.add_experiment('exp1', 20000, tad_def=exp4,
                                hic_data=PATH + '/20Kb/chrT/chrT_D.tsv')
        exp = test_chr.experiments['exp1']
        sum20 = sum(exp.hic_data[0])
        exp.set_resolution(80000)
        sum80 = sum(exp.hic_data[0])
        check_hic(exp.hic_data[0], exp.size)
        exp.set_resolution(160000)
        sum160 = sum(exp.hic_data[0])
        check_hic(exp.hic_data[0], exp.size)
        exp.set_resolution(360000)
        sum360 = sum(exp.hic_data[0])
        check_hic(exp.hic_data[0], exp.size)
        exp.set_resolution(2400000)
        sum2400 = sum(exp.hic_data[0])
        check_hic(exp.hic_data[0], exp.size)
        exp.set_resolution(40000)
        sum40 = sum(exp.hic_data[0])
        check_hic(exp.hic_data[0], exp.size)
        exp.set_resolution(20000)
        sum21 = sum(exp.hic_data[0])
        check_hic(exp.hic_data[0], exp.size)
        exp.set_resolution(40000)
        sum41 = sum(exp.hic_data[0])
        check_hic(exp.hic_data[0], exp.size)
        self.assertTrue(sum20 == sum80 == sum160 == sum360 == sum40 \
                        == sum21 == sum2400 == sum41)


    def test_09_hic_normalization(self):
        """
        writes interaction pair file.
        """
        test_chr = Chromosome(name='Test Chromosome', max_tad_size=260000)
        test_chr.add_experiment('exp1', 20000, tad_def=exp4,
                                hic_data=PATH + '/20Kb/chrT/chrT_D.tsv')
        exp = test_chr.experiments[0]
        exp.load_hic_data('20Kb/chrT/chrT_A.tsv', silent=True)
        exp.get_hic_zscores()
        exp.get_hic_zscores(zscored=False)
        sumz = sum([exp._zscores[k1][k2] for k1 in exp._zscores.keys()
                    for k2 in exp._zscores[k1]])
        self.assertEqual(round(sumz, 4), round(37.48799557280391, 4))


    def test_10_generate_weights(self):
        """
        method names are: 'sqrt' or 'over_tot'
        """
        test_chr = Chromosome(name='Test Chromosome', max_tad_size=260000)
        test_chr.add_experiment('exp1', 20000, tad_def=exp4,
                                hic_data=PATH + '/20Kb/chrT/chrT_D.tsv')
        exp = test_chr.experiments[0]
        tadbit_weigths = exp.norm[:]
        exp.norm = None
        exp.normalize_hic(method='sqrt')
        self.assertEqual(tadbit_weigths[0], exp.norm[0])


    def test_11_write_interaction_pairs(self):
        """
        writes interaction pair file.
        """
        test_chr = Chromosome(name='Test Chromosome', max_tad_size=260000)
        test_chr.add_experiment('exp1', 20000, tad_def=exp4,
                                hic_data=PATH + '/20Kb/chrT/chrT_D.tsv')
        exp = test_chr.experiments[0]
        exp.load_hic_data('20Kb/chrT/chrT_A.tsv', silent=True)
        exp.get_hic_zscores()
        exp.get_hic_zscores(zscored=False)
        exp.write_interaction_pairs('lala')
        lines = open('lala').readlines()
        self.assertEqual(len(lines), 4674)
        self.assertEqual(lines[25], '1\t28\t0.00796578796261\n')
        self.assertEqual(lines[2000], '26\t70\t0.00109722560121\n')
        system('rm -f lala')


    def test_12_3d_modelling_optimization(self):
        """
        quick test to generate 3D coordinates from 3? simple models???
        """
        try:
            __import__('IMP')
        except ImportError:
            warn('IMP not found, skipping test\n')
            return
        test_chr = Chromosome(name='Test Chromosome', max_tad_size=260000)
        test_chr.add_experiment('exp1', 20000, tad_def=exp4,
                                hic_data=PATH + '/20Kb/chrT/chrT_D.tsv')
        exp = test_chr.experiments[0]
        exp.load_hic_data('20Kb/chrT/chrT_A.tsv', silent=True)
        exp.normalize_hic(method='visibility', silent=True)
        result = exp.optimal_imp_parameters(50,70, n_cpus=2,
                                            n_models=10, n_keep=2,
                                            lowfreq_range=(-0.6, 0, 0.5),
                                            upfreq_range=(0, 1.1, 1),
                                            maxdist_range=(500, 1000, 500),
                                            verbose=False)
        _, axes_range, result = result

        # get best correlations
        sort_result =  sorted([(result[i, j, k, l], axes_range[0][i],
                                axes_range[1][j], axes_range[2][l],
                                axes_range[3][k])
                               for i in range(len(axes_range[0]))
                               for j in range(len(axes_range[1]))
                               for k in range(len(axes_range[3]))
                               for l in range(len(axes_range[2]))
                               if str(result[i, j, k, l]) != '--'],
                              key=lambda x: x[0],
                              reverse=True)[0]
        wanted = (0.71387060499157218, 0.005, 500, 1.0, -0.59999999999999998)
        self.assertEqual([round(i, 4)for i in sort_result],
                         [round(i, 4)for i in wanted])


    def test_13_3d_modelling_centroid(self):
        """
        quick test to generate 3D coordinates from 3? simple models???
        """
        try:
            __import__('IMP')
        except ImportError:
            warn('IMP not found, skipping test\n')
            return
        test_chr = Chromosome(name='Test Chromosome', max_tad_size=260000)
        test_chr.add_experiment('exp1', 20000, tad_def=exp4,
                                hic_data=PATH + '/20Kb/chrT/chrT_D.tsv')
        exp = test_chr.experiments[0]
        exp.load_hic_data('20Kb/chrT/chrT_A.tsv', silent=True)
        exp.normalize_hic(method='visibility', silent=True)
        models = exp.model_region(50, 70, n_models=110, n_keep=25,
                                  n_cpus=2,
                                  config={'kforce': 5, 'maxdist': 500,
                                          'scale': 0.005,
                                          'upfreq': 1.0, 'lowfreq': -0.6})
        models.save_models('models.pick')
        
        avg = models.average_model()
        xis = [256.800659, 192.261123, 140.659133, 100.450248, 46.9496421,
               -86.281616, -162.32574, -224.36425, -265.56039, -113.91905,
               -12.291224, -2.0760805, -141.23983, -132.74307, 25.4968967,
               45.7021636, -20.619169, 2.43585228, 39.3904533, 132.945693,
               178.332595]
        yis = [777.838989, 653.305297, 523.345275, 392.911132, 257.727813,
               353.407135, 273.915130, 151.659851, 257.066864, 165.820938,
               78.4026641, -63.092754, -134.39276, -258.01034, -258.30206,
               -398.19586, -527.28540, -659.35449, -542.74645, -551.93316,
               -492.08663]
        zis = [-779.30718, -654.69604, -526.70159, -396.44201, -264.52145,
               -344.05822, -272.64324, -143.98304, -240.02696, -157.30371,
               -78.534126, 60.9385299, 168.089416, 279.031097, 252.534454,
               390.181549, 469.284545, 607.548950, 548.516906, 551.545471,
               530.545471]
        self.assertEqual([round(x, 3) for x in avg['x']],
                         [round(x, 3) for x in xis])
        self.assertEqual([round(x, 3) for x in avg['y']],
                         [round(x, 3) for x in yis])
        self.assertEqual([round(x, 3) for x in avg['z']],
                         [round(x, 3) for x in zis])

        centroid = models.centroid_model()
        self.assertEqual(centroid['rand_init'], 69)


    def test_14_3d_clustering(self):
        """
        """
        models = load_structuralmodels('models.pick')
        wnt = {1: [95, 69, 101, 55, 94, 81, 30, 32, 25,
                   72, 52, 56, 2, 98, 89, 40],
               2: [92, 78, 97, 43, 31, 54, 62, 28, 13]}
        if find_executable('mcl'):
            models.cluster_models(method='mcl', verbose=False)
            self.assertEqual(models.clusters, wnt)
        models.cluster_models(method='ward', verbose=False)
        self.assertEqual(models.clusters, wnt)


    def test_15_3d_modelling(self):
        """
        """
        models = load_structuralmodels('models.pick') 
        models.cluster_models(method='ward', verbose=False)
        # density
        models.density_plot(savedata='lala', plot=False)
        lines = open('lala').readlines()
        self.assertEqual(len(lines), 22)
        self.assertEqual(lines[1], '1\t99.988\t100.022\tNone\tNone\tNone\tNone\tNone\tNone\tNone\tNone\n')
        self.assertEqual(lines[15], '15\t99.939\t99.985\t99.969\t99.998\t99.97\t99.998\t99.974\t99.996\t99.977\t100.0\n')
        # contacts
        cmap = models.get_contact_matrix(cutoff=300)
        self.assertEqual(round(
            sum([i if i >=0 else 0 for i in reduce(lambda x, y: x+y, cmap)]),
            3), 80.8)
        # define best models
        models.define_best_models(10)
        self.assertEqual(len(models), 10)
        m1 = models[9]
        models.define_best_models(25)
        self.assertEqual(len(models), 25)
        self.assertEqual(m1, models[9])
        # correlation
        corr, pval = models.correlate_with_real_data(cutoff=300)
        self.assertEqual(round(corr, 4), round(0.63597740365044708, 4))
        self.assertEqual(round(pval, 4), round(0, 4))
        # consistency
        models.model_consistency(plot=False, savedata='lala')
        lines = open('lala').readlines()
        self.assertEqual(len(lines), 22)
        self.assertEqual(lines[1], '1\t11.0\t25.667\t40.667\t50.667\n')
        self.assertEqual(lines[15], '15\t94.667\t100.0\t100.0\t100.0\n')
        # measure angle
        self.assertEqual(round(models.angle_between_3_particles(2,8,15), 3), 128.338)
        self.assertEqual(round(models.angle_between_3_particles(19,20,21), 3), 60.163)
        self.assertEqual(round(models.angle_between_3_particles(15,14,11), 3), 64.474)
        # coordinates
        self.assertEqual([round(x, 3) for x in models.particle_coordinates(15)],
                         [2372.253, -1193.602, -1145.397])
        # dihedral_angle
        self.assertEqual(round(models.dihedral_angle(2,8,15, 16), 3), -13.443)
        self.assertEqual(round(models.dihedral_angle(15,19,20,21), 3), 79.439)
        self.assertEqual(round(models.dihedral_angle(15,14,11, 12), 3), 8.136)
        # median distance
        self.assertEqual(round(models.median_3d_dist(3, 20, plot=False), 3), 1553.974)
        self.assertEqual(round(models.median_3d_dist(3, 20, cluster=1, plot=False), 3), 1522.16)
        self.assertEqual(round(models.median_3d_dist(7, 10, models=range(5), plot=False), 3), 266.024)
        # write cmm
        models.write_cmm('.', model_num=2)
        models.write_cmm('.', models=range(5))
        models.write_cmm('.', cluster=2)
        # write xyz
        models.write_xyz('.', model_num=2)
        models.write_xyz('.', models=range(5))
        models.write_xyz('.', cluster=2)
        # clean
        system('rm -f model.*')
        system('rm -f lala')
        

    def test_16_tadbit_c(self):
        """
        Runs tests written in c, around the detection of TADs
        """
        print '\n\nC SIDE'
        print '------'
        chdir(PATH + '/../src/test/')
        system('make clean')
        system('make')
        return_code = system('make test')
        chdir(PATH)
        self.assertEqual(return_code, 0)


if __name__ == "__main__":
    unittest.main()
    
