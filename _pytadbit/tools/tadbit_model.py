"""

information needed

 - path working directory with mapped reads or list of SAM/BAM/MAP files

"""

from argparse                     import HelpFormatter
from os                           import path, listdir, remove
from string                       import ascii_letters
from random                       import random
from shutil                       import copyfile
from pytadbit.imp.imp_modelling   import generate_3d_models, TADbitModelingOutOfBound
from pytadbit                     import load_structuralmodels
from pytadbit                     import Chromosome
from pytadbit.utils.file_handling import mkdir
from pytadbit.utils.sqlite_utils  import get_path_id, add_path, print_db, get_jobid
from pytadbit.utils.sqlite_utils  import digest_parameters
from pytadbit                     import load_hic_data_from_reads
from itertools                    import product
from warnings                     import warn
from numpy                        import arange
from cPickle                      import load
import sqlite3 as lite
import time


DESC = ("Generates 3D models given an input interaction matrix and a set of "
        "input parameters")

def write_one_job(opts, rand, m, u, l, s, job_file_handler):
    (m, u, l, s) = tuple(map(my_round, (m, u, l, s)))
    job_file_handler.write(
        'tadbit model -w %s -r %d -C %d --input_matrix %s '
        '--maxdist %s --upfreq %s --lowfreq=%s '
        '--scale %s --rand %s --nmodels %s --nkeep %s '
        '--beg %d --end %d --perc_zero %f %s\n' % (
            opts.workdir, opts.reso,
            min(opts.cpus, opts.nmodels_run), opts.matrix,
            m, u, l, s, rand,
            opts.nmodels_run, # equal to nmodels if not defined
            opts.nkeep, # keep, equal to nmodel_run if defined
            opts.beg * opts.reso, opts.end * opts.reso,
            opts.perc_zero,
            '--optimize ' if opts.optimize else ''))

def run_batch_job(exp, opts, m, u, l, s, outdir):
    zscores, values, zeros = exp._sub_experiment_zscore(opts.beg, opts.end)
    zeros = tuple([i not in zeros for i in xrange(opts.end - opts.beg + 1)])
    nloci = opts.end - opts.beg + 1
    coords = {"crm"  : opts.crm,
              "start": opts.beg,
              "end"  : opts.end}

    optpar = {'maxdist': m,
              'upfreq' : u,
              'lowfreq': l,
              'scale'  : s,
              'kforce' : 5}

    models = generate_3d_models(zscores, opts.reso, nloci,
                                values=values, n_models=opts.nmodels,
                                n_keep=opts.nkeep,
                                n_cpus=opts.cpus, keep_all=True,
                                start=int(opts.rand), container=None,
                                config=optpar, coords=coords,
                                zeros=zeros)
    # Save models
    muls = tuple(map(my_round, (m, u, l, s)))
    models.save_models(
        path.join(outdir, 'cfg_%s_%s_%s_%s' % muls,
                  ('models_%s-%s.pick' % (opts.rand, int(opts.rand) + opts.nmodels))
                  if opts.nmodels > 1 else 
                  ('model_%s.pick' % (opts.rand))))

def my_round(num, val=4):
    num = round(float(num), val)
    return str(int(num) if num == int(num) else num)

def optimization(exp, opts, job_file_handler, outdir):
    models = compile_models(opts, outdir)
    print 'Optimizing parameters...'
    print ('# %3s %6s %7s %7s %6s\n' % (
        "num", "upfrq", "lowfrq", "maxdist",
        "scale"))
    for m, u, l, s in product(opts.maxdist, opts.upfreq, opts.lowfreq, opts.scale):
        muls = tuple(map(my_round, (m, u, l, s)))
        if muls in models:
            print('%5s %6s %7s %7s %6s  ' % ('x', u, l, m, s))
            continue
        elif opts.job_list:
            print('%5s %6s %7s %7s %6s  ' % ('o', u, l, m, s))
        else:
            print('%5s %6s %7s %7s %6s  ' % ('-', u, l, m, s))
        mkdir(path.join(outdir, 'cfg_%s_%s_%s_%s' % muls))

        # write list of jobs to be run separately
        if opts.job_list:
            for rand in xrange(1, opts.nmodels + 1, opts.nmodels_run):
                write_one_job(opts, rand, m, u, l, s, job_file_handler)
            continue

        # compute models
        try:
            run_batch_job(exp, opts, m, u, l, s, outdir)
        except TADbitModelingOutOfBound:
            warn('WARNING: scale (here %s) x resolution (here %d) should be '
                 'lower than maxdist (here %d instead of at least: %d)' % (
                     s, opts.reso, m, s * opts.reso))
            continue

    if opts.job_list:
        job_file_handler.close()

def correlate_models(opts, outdir, exp, corr='spearman', off_diag=1,
                     verbose=True):
    models = compile_models(opts, outdir, exp=exp, ngood=opts.nkeep)
    results = {}
    if verbose:
        print ('# %7s %6s %7s %7s %6s %7s\n' % (
            "num", "upfrq", "lowfrq", "maxdist",
            "scale", "cutoff"))
    for num, (m, u, l, s) in enumerate(models, 1):
        muls = tuple(map(my_round, (m, u, l, s)))
        result = 0
        d = float('nan')
        for cutoff in opts.dcutoff:
            sub_result = models[muls].correlate_with_real_data(
                cutoff=(int(cutoff * opts.reso * float(s))),
                corr=corr, off_diag=off_diag)[0]
            try:
                sub_result = models[muls].correlate_with_real_data(
                    cutoff=(int(cutoff * opts.reso * float(s))),
                    corr=corr, off_diag=off_diag)[0]
                if result < sub_result:
                    result = sub_result
                    d = cutoff
            except Exception, e:
                print '  SKIPPING: %s' % e
                result = 0
        if verbose:
            print('%5s/%-5s %6s %7s %7s %6s %6s %.4f' % (num, len(models),
                                                        u, l, m, s, d, result))
        results[muls] = result
    # get the best combination
    best= (None, [None, None, None, None, None])
    for m, u, l, d, s in results:
        mulds = tuple(map(my_round, (m, u, l, d, s)))
        if results[mulds] > best[0]:
            best = results[mulds], [u, l, m, s, d]
    if verbose:
        print 'Best combination:'
        print('  %5s     %6s %7s %7s %6s %6s %.4f' % tuple(['=>'] + best[1] + [best[0]]))

    u, l, m, s, d = best[1]
    optpar = {'maxdist': m,
              'upfreq' : u,
              'lowfreq': l,
              'scale'  : s,
              'kforce' : 5}
    return optpar, d
    
def big_run(exp, opts, job_file_handler, outdir, optpar):
    m, u, l, s = (optpar['maxdist'], 
                  optpar['upfreq' ],
                  optpar['lowfreq'],
                  optpar['scale'  ])
    muls = tuple(map(my_round, (m, u, l, s)))
    # this to take advantage of previously runned models
    models = compile_models(opts, outdir, wanted=muls)[muls]
    models.define_best_models(len(models) + len(models._bad_models))
    runned = [int(mod['rand_init']) for mod in models]
    start = str(max(runned))
    # reduce number of models to run
    opts.nmodels -= len(runned)
    
    if opts.rand == '1':
        print 'Using %s precalculated models with m:%s u:%s l:%s s:%s ' % (start, m, u, l, s)
        opts.rand = str(int(start) + 1)
    elif opts.rand != '1' and int(opts.rand) < int(start):
        raise Exception('ERROR: found %s precomputed models, use a higher '
                        'rand. init. number or delete the files')
    
    print 'Computing %s models' % len(opts.nmodels)
    if opts.job_list:
        # write jobs
        for rand in xrange(start, opts.nmodels + start, opts.nmodels_run):
            write_one_job(opts, rand, m, u, l, s, job_file_handler)
        job_file_handler.close()
        return
    
    # compute models
    try:
        run_batch_job(exp, opts, m, u, l, s, outdir)
    except TADbitModelingOutOfBound:
        warn('WARNING: scale (here %s) x resolution (here %d) should be '
             'lower than maxdist (here %d instead of at least: %d)' % (
                 s, opts.reso, m, s * opts.reso))

def run(opts):
    check_options(opts)

    launch_time = time.localtime()

    # prepare output folders
    mkdir(path.join(opts.workdir, '06_model'))
    outdir = path.join(opts.workdir, '06_model',
                       'chr%s_%s-%s' % (opts.crm, opts.beg, opts.end))
    mkdir(outdir)

    # load data
    if opts.matrix:
        crm = load_hic_data(opts)
    else:
        (bad_co, bad_co_id, biases, biases_id,
         mreads, mreads_id, reso) = load_parameters_fromdb(opts)
        hic_data = load_hic_data_from_reads(mreads, reso)
        hic_data.bads = dict((int(l.strip()), True) for l in open(bad_co))
        hic_data.bias = dict((int(l.split()[0]), float(l.split()[1]))
                             for l in open(biases))
        
    exp = crm.experiments[0]
    opts.beg, opts.end = opts.beg or 1, opts.end or exp.size

    # in case we are not going to run
    if opts.job_list:
        job_file_handler = open(path.join(outdir, 'job_list.q'), 'w')
    else:
        job_file_handler = None

    # optimization
    if opts.optimize:
        optimization(exp, opts, job_file_handler, outdir)
        finish_time = time.localtime()
        return

    # correlate all optimizations and get best set of parqameters
    optpar, dcutoff = correlate_models(opts, outdir, exp)

    # run good mmodels
    big_run(exp, opts, job_file_handler, outdir, optpar)

    finish_time = time.localtime()

    # save all job information to sqlite DB
    # save_to_db(opts, counts, multis, f_names1, f_names2, out_file1, out_file2,
    #            launch_time, finish_time)

def compile_models(opts, outdir, exp=None, ngood=None, wanted=None):
    if exp:
        zscores, _, zeros = exp._sub_experiment_zscore(opts.beg, opts.end)
        zeros = tuple([i not in zeros for i in xrange(opts.end - opts.beg + 1)])
    models = {}
    for cfg_dir in listdir(outdir):
        if not cfg_dir.startswith('cfg_'):
            continue
        _, m, u, l, s = cfg_dir.split('_')
        muls = m, u, l, s
        m, u, l, s = int(m), float(u), float(l), float(s)
        if wanted and muls != wanted:
            continue
        for fmodel in listdir(path.join(outdir, cfg_dir)):
            if not fmodel.startswith('models_'):
                continue
            if not muls in models:
                # print 'create new optimization entry', m, u, l, s, fmodel
                models[muls] = load_structuralmodels(path.join(
                    outdir, cfg_dir, fmodel))
            else:
                # print 'populate optimization entry', m, u, l, s, fmodel
                sm = load(open(path.join(outdir, cfg_dir, fmodel)))
                if models[muls]._config != sm['config']:
                    raise Exception('ERROR: clean directory, hetergoneous data')
                models[muls]._extend_models(sm['models'])
                models[muls]._extend_models(sm['bad_models'])
            if exp:
                models[muls].experiment = exp
                models[muls]._zscores   = zscores
                models[muls]._zeros     = zeros
            if ngood:
                models[muls].define_best_models(ngood)
    return models

def save_to_db(opts, counts, multis, f_names1, f_names2, out_file1, out_file2,
               launch_time, finish_time):
    if 'tmpdb' in opts and opts.tmpdb:
        # check lock
        while path.exists(path.join(opts.workdir, '__lock_db')):
            time.sleep(0.5)
        # close lock
        open(path.join(opts.workdir, '__lock_db'), 'a').close()
        # tmp file
        dbfile = opts.tmpdb
        try: # to copy in case read1 was already mapped for example
            copyfile(path.join(opts.workdir, 'trace.db'), dbfile)
        except IOError:
            pass
    else:
        dbfile = path.join(opts.workdir, 'trace.db')
    con = lite.connect(dbfile)
    with con:
        cur = con.cursor()
        cur.execute("""SELECT name FROM sqlite_master WHERE
                       type='table' AND name='PARSED_OUTPUTs'""")
        if not cur.fetchall():
            cur.execute("""
        create table MAPPED_OUTPUTs
           (Id integer primary key,
            PATHid int,
            BEDid int,
            Uniquely_mapped int,
            unique (PATHid, BEDid))""")
            cur.execute("""
        create table PARSED_OUTPUTs
           (Id integer primary key,
            PATHid int,
            Total_interactions int,
            Multiples int,
            unique (PATHid))""")
        try:
            parameters = digest_parameters(opts, get_md5=False)
            param_hash = digest_parameters(opts, get_md5=True )
            cur.execute("""
    insert into JOBs
     (Id  , Parameters, Launch_time, Finish_time,    Type, Parameters_md5)
    values
     (NULL,       '%s',        '%s',        '%s', 'Parse',           '%s')
     """ % (parameters,
            time.strftime("%d/%m/%Y %H:%M:%S", launch_time),
            time.strftime("%d/%m/%Y %H:%M:%S", finish_time), param_hash))
        except lite.IntegrityError:
            pass
        jobid = get_jobid(cur)
        add_path(cur, out_file1, 'BED', jobid, opts.workdir)
        for genome in opts.genome:
            add_path(cur, genome, 'FASTA', jobid, opts.workdir)
        if out_file2:
            add_path(cur, out_file2, 'BED', jobid, opts.workdir)
        fnames = f_names1, f_names2
        outfiles = out_file1, out_file2
        for count in counts:
            try:
                sum_reads = 0
                for i, item in enumerate(counts[count]):
                    cur.execute("""
                    insert into MAPPED_OUTPUTs
                    (Id  , PATHid, BEDid, Uniquely_mapped)
                    values
                    (NULL,    %d,     %d,      %d)
                    """ % (get_path_id(cur, fnames[count][i], opts.workdir),
                           get_path_id(cur, outfiles[count], opts.workdir),
                           counts[count][item]))
                    sum_reads += counts[count][item]
            except lite.IntegrityError:
                print 'WARNING: already parsed (MAPPED_OUTPUTs)'
            try:
                cur.execute("""
                insert into PARSED_OUTPUTs
                (Id  , PATHid, Total_interactions, Multiples)
                values
                (NULL,     %d,      %d,        %d)
                """ % (get_path_id(cur, outfiles[count], opts.workdir),
                       sum_reads, multis[count]))
            except lite.IntegrityError:
                print 'WARNING: already parsed (PARSED_OUTPUTs)'
        print_db(cur, 'MAPPED_INPUTs')
        print_db(cur, 'PATHs')
        print_db(cur, 'MAPPED_OUTPUTs')
        print_db(cur, 'PARSED_OUTPUTs')
        print_db(cur, 'JOBs')
    if 'tmpdb' in opts and opts.tmpdb:
        # copy back file
        copyfile(dbfile, path.join(opts.workdir, 'trace.db'))
        remove(dbfile)
    # release lock
    try:
        remove(path.join(opts.workdir, '__lock_db'))
    except OSError:
        pass

def populate_args(parser):
    """
    parse option from call
    """
    parser.formatter_class=lambda prog: HelpFormatter(prog, width=95,
                                                      max_help_position=27)

    glopts = parser.add_argument_group('General options')

    glopts.add_argument('--job_list', dest='job_list', action='store_true',
                      default=False,
                      help='generate a a file with a list of jobs to be run in '
                        'a cluster')

    glopts.add_argument('-w', '--workdir', dest='workdir', metavar="PATH",
                        action='store', default=None, type=str, required=True,
                        help='''path to working directory (generated with the
                        tool tadbit mapper)''')
    glopts.add_argument('--optimize', dest='optimize', 
                        default=False, action="store_true",
                        help='''optimization run, store less info about models''')
    glopts.add_argument('--rand', dest='rand', metavar="INT",
                        type=str, default='1', 
                        help='''[%(default)s] random initial number. NOTE:
                        when running single model at the time, should be
                        different for each run''')
    glopts.add_argument('--crm', dest='crm', metavar="NAME",
                        help='chromosome name')
    glopts.add_argument('--beg', dest='beg', metavar="INT", type=float,
                        default=None,
                        help='genomic coordinate from which to start modeling')
    glopts.add_argument('--end', dest='end', metavar="INT", type=float,
                        help='genomic coordinate where to end modeling')
    glopts.add_argument('-r', '--reso', dest='reso', metavar="INT", type=int,
                        help='resolution of the Hi-C experiment')
    glopts.add_argument('--input_matrix', dest='matrix', metavar="PATH",
                        type=str,
                        help='''In case input was not generated with the TADbit
                        tools''')

    glopts.add_argument('--nmodels_run', dest='nmodels_run', metavar="INT",
                        default=None, type=int,
                        help='[ALL] number of models to run with this call')

    glopts.add_argument('--nmodels', dest='nmodels', metavar="INT",
                        default=5000, type=int,
                        help=('[%(default)s] number of models to generate for' +
                              ' modeling'))

    glopts.add_argument('--nkeep', dest='nkeep', metavar="INT",
                        default=1000, type=int,
                        help=('[%(default)s] number of models to keep for ' +
                        'modeling'))
    glopts.add_argument('--perc_zero', dest='perc_zero', metavar="FLOAT",
                        type=float, default=90)

    glopts.add_argument('--maxdist', action='store', metavar="LIST",
                        default='400', dest='maxdist',
                        help='range of numbers for maxdist' +
                        ', i.e. 400:1000:100 -- or just a number')
    glopts.add_argument('--upfreq', dest='upfreq', metavar="LIST",
                        default='0',
                        help='range of numbers for upfreq' +
                        ', i.e. 0:1.2:0.3 --  or just a number')
    glopts.add_argument('--lowfreq', dest='lowfreq', metavar="LIST",
                        default='0',
                        help='range of numbers for lowfreq' +
                        ', i.e. -1.2:0:0.3 -- or just a number')
    glopts.add_argument('--scale', dest='scale', metavar="LIST",
                        default="0.01",
                        help='[%(default)s] range of numbers to be test as ' +
                        'optimal scale value, i.e. 0.005:0.01:0.001 -- Can ' +
                        'also pass only one number')
    glopts.add_argument('--dcutoff', dest='dcutoff', metavar="LIST",
                        default="2",
                        help='[%(default)s] range of numbers to be test as ' +
                        'optimal distance cutoff parameter (distance, in ' +
                        'number of beads, from which to consider 2 beads as ' +
                        'being close), i.e. 1:5:0.5 -- Can also pass only one' +
                        ' number')
    glopts.add_argument("-C", "--cpu", dest="cpus", type=int,
                        default=1, help='''[%(default)s] Maximum number of CPU
                        cores  available in the execution host. If higher
                        than 1, tasks with multi-threading
                        capabilities will enabled (if 0 all available)
                        cores will be used''')
    glopts.add_argument('--tmpdb', dest='tmpdb', action='store', default=None,
                        metavar='PATH', type=str,
                        help='''if provided uses this directory to manipulate the
                        database''')

    parser.add_argument_group(glopts)

def check_options(opts):
    # check resume
    if not path.exists(opts.workdir):
        raise IOError('ERROR: wordir not found.')
    # do the division to bins
    try:
        opts.beg = int(float(opts.beg) / opts.reso)
        opts.end = int(float(opts.end) / opts.reso)
        if opts.end - opts.beg <= 2:
            raise Exception('"beg" and "end" parameter should be given in ' +
                            'genomic coordinates, not bin')
    except TypeError:
        pass

    # turn options into lists
    opts.scale   = (tuple(arange(*[float(s) for s in opts.scale.split(':')  ]))
                    if ':' in opts.scale   else [float(opts.scale  )])
    
    opts.maxdist = (tuple(range (*[int  (i) for i in opts.maxdist.split(':')]))
                    if ':' in opts.maxdist else [int  (opts.maxdist)])

    opts.upfreq  = (tuple(arange(*[float(i) for i in opts.upfreq.split(':') ]))
                    if ':' in opts.upfreq  else [float(opts.upfreq )])

    opts.lowfreq = (tuple(arange(*[float(i) for i in opts.lowfreq.split(':')]))
                    if ':' in opts.lowfreq else [float(opts.lowfreq)])

    opts.dcutoff = (tuple(arange(*[float(i) for i in opts.dcutoff.split(':')]))
                    if ':' in opts.dcutoff else [float(opts.dcutoff)])

    opts.nmodels_run = opts.nmodels_run or opts.nmodels

    if opts.matrix:
        opts.matrix  = path.abspath(opts.matrix)
    opts.workdir = path.abspath(opts.workdir)

    mkdir(opts.workdir)
    if 'tmpdb' in opts and opts.tmpdb:
        dbdir = opts.tmpdb
        # tmp file
        dbfile = 'trace_%s' % (''.join([ascii_letters[int(random() * 52)]
                                        for _ in range(10)]))
        opts.tmpdb = path.join(dbdir, dbfile)

def load_parameters_fromdb(opts):
    if 'tmpdb' in opts and opts.tmpdb:
        dbfile = opts.tmpdb
    else:
        dbfile = path.join(opts.workdir, 'trace.db')
    con = lite.connect(dbfile)
    with con:
        cur = con.cursor()
        if not opts.jobid:
            # get the JOBid of the parsing job
            cur.execute("""
            select distinct Id from JOBs
            where Type = 'Normalize'
            """)
            jobids = cur.fetchall()
            if len(jobids) > 1:
                raise Exception('ERROR: more than one possible input found, use'
                                '"tadbit describe" and select corresponding '
                                'jobid with --jobid')
            parse_jobid = jobids[0][0]
        else:
            parse_jobid = opts.jobid
        # fetch path to parsed BED files
        cur.execute("""
        select distinct Path, PATHs.Id from PATHs
        where paths.jobid = %s and paths.Type = 'BAD_COLUMNS'
        """ % parse_jobid)
        bad_co, bad_co_id  = cur.fetchall()[0]
        cur.execute("""
        select distinct Path, PATHs.Id from PATHs
        where paths.jobid = %s and paths.Type = 'BIASES'
        """ % parse_jobid)
        biases, biases_id = cur.fetchall()[0]
        cur.execute("""
        select distinct Path, PATHs.Id from PATHs
        inner join NORMALIZE_OUTPUTs on PATHs.Id = NORMALIZE_OUTPUTs.Input
        where NORMALIZE_OUTPUTs.JOBid = %d;
        """ % parse_jobid)
        mreads, mreads_id = cur.fetchall()[0]
        cur.execute("""
        select distinct Resolution from NORMALIZE_OUTPUTs
        where NORMALIZE_OUTPUTs.JOBid = %d;
        """ % parse_jobid)
        reso = int(cur.fetchall()[0][0])
        return (bad_co, bad_co_id, biases, biases_id,
                mreads, mreads_id, reso)

def load_hic_data(opts):
    """
    Load Hi-C data
    """
    # Start reading the data
    crm = Chromosome(opts.crm) # Create chromosome object

    crm.add_experiment('test', exp_type='Hi-C', resolution=opts.reso,
                       norm_data=opts.matrix)
    # TODO: if not bad columns:...
    crm.experiments[-1].filter_columns(perc_zero=opts.perc_zero)
    if opts.beg > crm.experiments[-1].size:
        raise Exception('ERROR: beg parameter is larger than chromosome size.')
    if opts.end > crm.experiments[-1].size:
        print ('WARNING: end parameter is larger than chromosome ' +
               'size. Setting end to %s.\n' % (crm.experiments[-1].size *
                                               opts.reso))
        opts.end = crm.experiments[-1].size
    return crm
