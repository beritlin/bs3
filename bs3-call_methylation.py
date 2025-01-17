#!/usr/bin/env python

from optparse import OptionParser, OptionGroup
from bs_utils.utils import *
import subprocess
try :
    import pysam
except ImportError :
    print "[Error] Cannot import \"pysam\" package. Have you installed it?"
    exit(-1)

import gzip


"""
def context_calling(seq, position):

    word=seq[position]
    word=word.upper()

    context="--"
    context_CH="--"
    if position + 2 < len(seq) and position - 2 >= 0:

        if word == "C":
            word2 = seq[position+1]
            context_CH = word + word2
            if word2 == "G":
                context = "CG"
            elif word2 in ['A','C','T']:
                word3 = seq[position+2]
                if word3 == "G":
                    context = "CHG"
                elif word3 in ['A','C','T']:
                    context="CHH"

        elif word == "G":
            word2 = seq[position-1]
            context_CH = word + word2
            context_CH = context_CH.translate(string.maketrans("ATCG", "TAGC"))
            if word2 == "C":
                context = "CG"
            elif word2 in ['A','G','T']:
                word3 = seq[position-2]
                if word3 == "C":
                    context = "CHG"
                elif word3 in ['A','G','T']:
                    context = "CHH"

    return word, context, context_CH
"""


if __name__ == '__main__':

    parser = OptionParser()
    parser.add_option("-i", "--input", type="string", dest="infilename",help="BAM output from bs3-align", metavar="INFILE")
    parser.add_option("-d", "--db", type="string", dest="dbpath",help="Path to the reference genome library (generated in preprocessing genome) [Default: %default]" , metavar="DBPATH", default = reference_genome_path)
    parser.add_option("-o", "--output-prefix", type="string", dest="output_prefix",help="The output prefix to create ATCGmap and wiggle files [INFILE]", metavar="OUTFILE")
    parser.add_option("--sorted", action="store_true", dest="sorted",help="Specify when the input bam file is already sorted, the sorting step will be skipped [Default: %default]", default = False)

    parser.add_option("--wig", type="string", dest="wig_file",help="The output .wig file [INFILE.wig]", metavar="OUTFILE")
    parser.add_option("--CGmap", type="string", dest="CGmap_file",help="The output .CGmap file [INFILE.CGmap]", metavar="OUTFILE")
    parser.add_option("--ATCGmap", type="string", dest="ATCGmap_file",help="The output .ATCGmap file [INFILE.ATCGmap]", metavar="OUTFILE")

    parser.add_option("-x", "--rm-SX", action="store_true", dest="RM_SX",help="Removed reads with tag \'XS:i:1\', which would be considered as not fully converted by bisulfite treatment [Default: %default]", default = False)
    parser.add_option("--rm-CCGG", action="store_true", dest="RM_CCGG",help="Removed sites located in CCGG, avoiding the bias introduced by artificial DNA methylation status \'XS:i:1\', which would be considered as not fully converted by bisulfite treatment [Default: %default]", default = False)
    parser.add_option("--rm-overlap", action="store_true", dest="RM_OVERLAP",help="Removed one mate if two mates are overlapped, for paired-end data [Default: %default]", default = False)
    parser.add_option("--txt", action="store_true", dest="text",help="Show CGmap and ATCGmap in .gz [Default: %default]", default = False)

    parser.add_option("-r", "--read-no",type = "int", dest="read_no",help="The least number of reads covering one site to be shown in wig file [Default: %default]", default = 1)
    parser.add_option("-v", "--version", action="store_true", dest="version",help="show version of BS-Seeker3", metavar="version", default = False)

    (options, args) = parser.parse_args()


    # if no options were given by the user, print help and exit
    if len(sys.argv) == 1:
        parser.print_help()
        exit(0)

    if options.version :
        show_version()
        exit (-1)
    else :
        show_version()


    if options.infilename is None:
        error('-i option is required')
    if not os.path.isfile(options.infilename):
        error('Cannot find input file: %s' % options.infilename)

    open_log(options.infilename+'.call_methylation_log')
    db_d = lambda fname:  os.path.join( os.path.expanduser(options.dbpath), fname) # bug fixed, weilong

    if options.RM_OVERLAP :
        logm("The option \"--rm-overlap\" is specified, thus overlap regions of two mates would be discarded.")

    subprocess.call('samtools view -bS ' + options.infilename + '  | samtools sort -o output,bam', shell = True)
    logm('indexing sorted alignments')
    subprocess.call('samtools index output.bam output.bai', shell = True)
    logm('calculating methylation levels')

    if options.text :
        ATCGmap_fname = options.ATCGmap_file or ((options.output_prefix or options.infilename) + '.ATCGmap')
        ATCGmap = open(ATCGmap_fname, 'w')

        CGmap_fname = options.CGmap_file or ((options.output_prefix or options.infilename) + '.CGmap')
        CGmap = open(CGmap_fname, 'w')
    else :
        ATCGmap_fname = options.ATCGmap_file or ((options.output_prefix or options.infilename) + '.ATCGmap.gz')
        ATCGmap = gzip.open(ATCGmap_fname, 'wb')

        CGmap_fname = options.CGmap_file or ((options.output_prefix or options.infilename) + '.CGmap.gz')
        CGmap = gzip.open(CGmap_fname, 'wb')

    # to improve the performance
    options_RM_CCGG = options.RM_CCGG
    options_read_no = options.read_no
    options_RM_SX = options.RM_SX
    options_RM_OVERLAP = options.RM_OVERLAP

    wiggle_fname = options.wig_file or ((options.output_prefix or options.infilename) + '.wig')
    wiggle = open(wiggle_fname, 'w')
    wiggle.write('type wiggle_0\n')

    sorted_input = pysam.Samfile('output.bam', 'rb')
    
    chrom = None
    nucs = ['A', 'T', 'C', 'G', 'N']
    ATCG_fwd = dict((n, 0) for n in nucs)
    ATCG_rev = dict((n, 0) for n in nucs)

    # Define the context and subcontext exchanging dictionary
    ContextTable={"CAA":"CHH", "CAC":"CHH", "CAG":"CHG", "CAT":"CHH",
                  "CCA":"CHH", "CCC":"CHH", "CCG":"CHG", "CCT":"CHH",
                  "CGA":"CG",  "CGC":"CG",  "CGG":"CG",  "CGT":"CG",
                  "CTA":"CHH", "CTC":"CHH", "CTG":"CHG", "CTT":"CHH"}
    #
    SubContextTable={"CAA":"CA", "CAC":"CA", "CAG":"CA", "CAT":"CA",
                     "CCA":"CC", "CCC":"CC", "CCG":"CC", "CCT":"CC",
                     "CGA":"CG", "CGC":"CG", "CGG":"CG", "CGT":"CG",
                     "CTA":"CT", "CTC":"CT", "CTG":"CT", "CTT":"CT"}
    #
    AntisenseContextTable=\
                 {"TTG":"CHH", "TGG":"CHH", "TCG":"CG", "TAG":"CHH",
                  "GTG":"CHH", "GGG":"CHH", "GCG":"CG", "GAG":"CHH",
                  "CTG":"CHG", "CGG":"CHG", "CCG":"CG", "CAG":"CHG",
                  "ATG":"CHH", "AGG":"CHH", "ACG":"CG", "AAG":"CHH"}
    #
    AntisenseSubContextTable=\
                 {"TTG":"CA", "TGG":"CC", "TCG":"CG", "TAG":"CT",
                  "GTG":"CA", "GGG":"CC", "GCG":"CG", "GAG":"CT",
                  "CTG":"CA", "CGG":"CC", "CCG":"CG", "CAG":"CT",
                  "ATG":"CA", "AGG":"CC", "ACG":"CG", "AAG":"CT"}
    #
    #PileUp = sorted_input.pileup()
    #for col in PileUp:

    cnts = lambda d: '\t'.join(str(d[n]) for n in nucs)

    for col in sorted_input.pileup():
        col_chrom = sorted_input.getrname(col.tid)
        col_pos = col.pos
        if chrom != col_chrom:
            chrom = col_chrom
            chrom_seq = deserialize(db_d(chrom))
            wiggle.write('variableStep chrom=%s\n' % chrom)
            logm('Processing chromosome: %s' % chrom)
        #
        for n in nucs:
            ATCG_fwd[n] = 0
            ATCG_rev[n] = 0
        #
        #nuc, context, subcontext = context_calling(chrom_seq, col_pos)
        # Need to validate the following codes

        if 1 < col_pos < len(chrom_seq) - 2 :
            FiveMer = chrom_seq[(col_pos-2):(col_pos+3)].upper()
            nuc = FiveMer[2]
            if nuc == "C" :
                ThreeMer = FiveMer[2:5]
                subcontext = SubContextTable.get(ThreeMer, "--")
                context =  ContextTable.get(ThreeMer, "--")
            elif nuc == "G" :
                ThreeMer = FiveMer[0:3]
                subcontext = AntisenseSubContextTable.get(ThreeMer, "--")
                context =  AntisenseContextTable.get(ThreeMer, "--")
            else :
                context = "--"
                subcontext = "--"
        else :
            nuc = chrom_seq[col_pos].upper()
            context = "--"
            subcontext = "--"
        #
        total_reads = 0
        #
        if options_RM_CCGG :
            # To validate the outputs
            #print chrom_seq[ (max(col_pos-3, 0)):(col_pos+4) ].upper()
            if "CCGG" in chrom_seq[ (max(col_pos-3, 0)):(col_pos+4) ].upper() :
                #print "Removed ============"
                continue
            # ---321X123---
            # ---CCGG===---
            # ---===CCGG---
            #check_start_pos = (col_pos - 3) if col_pos>3 else 0
            #check_end_pos = (col_pos + 4) if col_pos+4<len(chrom_seq) else len(chrom_seq)
            #check_seq = chrom_seq[check_start_pos:check_end_pos].upper()
            #if "CCGG" in SevenMer :
                #print "Remove\t%s\n" % check_seq # for debug
            #    continue
        #
        if options_RM_OVERLAP :
            qname_pool = []
            del qname_pool[:]

        for pr in col.pileups:
        #     print pr
            pr_qpos = pr.query_position
           
            #
            if (not pr.indel) : # skip indels
                pr_alignment = pr.alignment
                #if ( (options_RM_SX) and (pr.alignment.tags[1][1] == 1) ):
                ##=== Fixed error reported by Roberto
                #print options_RM_SX,  dict(pr.alignment.tags)["XS"]
                #if ( (options_RM_SX) and (dict(pr.alignment.tags)["XS"] == 1) ):
                #if ( (options_RM_SX) and (dict(pr_alignment.tags).get("XS",0) == 1) ):
                if ( (options_RM_SX) and ( ('XS', 1) in pr_alignment.tags) ) : # faster
                    # print "Debug: ", options_RM_SX, pr.alignment.tags[1]
                    # when need to filter and read with tag (XS==1), then remove the reads
                    continue
                #print pr_alignment.tags
                #if pr.qpos >= len(pr_alignment.seq):
                #if pr.query_position >= len(pr_alignment.seq):
                if pr_qpos >= len(pr_alignment.seq):
                    print 'WARNING: read %s has an invalid alignment. Discarding.. ' % pr_alignment.qname
                    continue
                #print "qname= %s" % pr.alignment.qname
                #qname = pr_alignment.qname.replace( "#1", "").replace(".1", "")
                if options_RM_OVERLAP :
                    #qname = re.sub( "[\.\#]1$","",pr_alignment.qname)
                    #qname = pr_alignment.qname.replace( "#1", "").replace(".1", "")
                    pr_alignment_qname = pr_alignment.qname
                    qname = pr_alignment_qname[:-2] if pr_alignment_qname[-2] in ['.', '#'] else pr_alignment_qname
                    # "SRR121545.1" or "SRR121545#1" to "SRR121545"
                    if (qname in qname_pool) :
                        # remove the 2nd mate (the same qname with 1st qname)
                        #print "Remove the read with duplicate qname : %s" % qname
                        continue
                    qname_pool.append(qname)
                #read_nuc = pr_alignment.seq[pr.qpos]
                #read_nuc = pr_alignment.seq[pr.query_position]
                try :
                    read_nuc = pr_alignment.seq[pr_qpos]
                except :
                    continue
                #
                if pr_alignment.is_reverse:
                    try:
                    	ATCG_rev[read_nuc] += 1
		    except KeyError:
			ATCG_rev['N'] +=1
                else:
                    try:
                    	ATCG_fwd[read_nuc] += 1
		    except KeyError:
			ATCG_rev['N'] +=1
                #
                if (read_nuc != 'N') & (read_nuc in nucs):
                    total_reads += 1
            #print col_pos, qname_pool

        #cnts = lambda d: '\t'.join(str(d[n]) for n in nucs)
        fwd_counts = cnts(ATCG_fwd)
        rev_counts = cnts(ATCG_rev)

        meth_level = None
        meth_cytosines = 0
        unmeth_cytosines = 0

        if nuc == 'C':
            # plus strand: take the ratio of C's to T's from reads that come from the forward strand
            meth_cytosines = ATCG_fwd['C']
            unmeth_cytosines = ATCG_fwd['T']

        elif nuc == 'G':
            # minus strand: take the ratio of G's to A's from reads that come from the reverse strand
            meth_cytosines = ATCG_rev['G']
            unmeth_cytosines = ATCG_rev['A']

        all_cytosines = meth_cytosines + unmeth_cytosines
        if all_cytosines > 0:
            meth_level = float(meth_cytosines)/all_cytosines

        pos = col_pos + 1

        meth_level_string = str(round(meth_level, 2)) if meth_level is not None else 'na'
        ATCGmap.write('%(chrom)s\t%(nuc)s\t%(pos)d\t%(context)s\t%(subcontext)s\t%(fwd_counts)s\t%(rev_counts)s\t%(meth_level_string)s\n' % locals())

        try :
            #if (meth_level is not None) and (all_cytosines >= options_read_no):
            if (all_cytosines >= options_read_no):
            #    print all_cytosines
                if nuc == 'C':
                    wiggle.write('%d\t%.2f\n' % (pos, meth_level))
                else :
                    wiggle.write('%d\t-%.2f\n' % (pos, meth_level))
                #
                CGmap.write('%(chrom)s\t%(nuc)s\t%(pos)d\t%(context)s\t%(subcontext)s\t%(meth_level_string)s\t%(meth_cytosines)s\t%(all_cytosines)s\n' % locals())
                # CGmap file only show CG sites
        except TypeError :
            continue

    ATCGmap.close()
    CGmap.close()
    wiggle.close()

    logm('Call methylation is finished. ')
    logm('==============================')
    logm('Files are saved as:')
    logm('  Wiggle: %s'% wiggle_fname)
    logm('  ATCGMap: %s' % ATCGmap_fname)
    logm('  CGmap: %s' % CGmap_fname)

