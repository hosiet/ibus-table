# -*- coding: utf-8 -*-
# vim: set noet ts=4:
#
# scim-python
#
# Copyright (c) 2008-2008 Yu Yuwei <acevery@gmail.com>
#
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place, Suite 330,
# Boston, MA  02111-1307  USA
#
# $Id: $
#

import os
import os.path as path
import sqlite3
import tabdict
import uuid
import time
import re

patt_r = re.compile(r'c([ea])(\d):(.*)')
patt_p = re.compile(r'p(-{0,1}\d)(\d)')

# first make some number index we will used :)
#(MLEN, CLEN, M0, M1, M2, M3, M4, PHRASE, FREQ, USER_FREQ) = range (0,10)


class tabsqlitedb:
	'''Phrase database for tables'''
	def __init__(self, name = 'table.db', user_db = None, filename = None ):
		# first we use the Parse in tabdict, which transform the char(a,b,c,...) to int(1,2,3,...) to fasten the sql enquiry
		self.parse = tabdict.parse
		self.deparse = tabdict.deparse
		if filename:
			self.db = sqlite3.connect( filename )
			return
		
		# we try to copy the system db to /dev/shm
		tmpname = '/dev/shm/ibus/tables/%s' % path.basename(name)
		if not path.exists( tmpname ):
			if not path.exists ('/dev/shm'):
				# no /dev/shm, so we still use the disk db :'(
				tmpname = name
			else:
				if not path.exists ('/dev/shm/ibus/tables'):
					# we need to mkdir first
					os.system('mkdir -p /dev/shm/ibus/tables')
				# then we just copy the disk db to the dir :)
				os.system('cp %s %s' % (name, tmpname ) )
				
		# open system phrase db
		self.db = sqlite3.connect(  tmpname )
		try:
			self.db.execute( 'PRAGMA page_size = 8192; ' )
			self.db.execute( 'PRAGMA cache_size = 20000; ' )
			# increase the cache size to speedup sqlite enquiry
			self.db.execute( 'PRAGMA temp_store = MEMORY; ' )
			self.db.execute( 'PRAGMA synchronous = OFF; ' )
		except:
			print 'encountering error when init db'
			pass
		# create IME property table
		sqlstr = 'CREATE TABLE IF NOT EXISTS main.ime (attr TEXT, val TEXT);' 
		self.db.executescript( sqlstr )
		# make sure we have values in ime table.
		if not self.db.execute('SELECT * FROM main.ime;').fetchall():
			ime_keys={'name':'',
					  'name.zh_cn':'',
					  'name.zh_hk':'',
					  'name.zh_tw':'',
					  'author':'somebody', 
					  'uuid':'%s' % uuid.uuid4(),
					  'serial_number':'%s' % time.strftime('%Y%m%d'),
					  'icon':'/usr/share/scim/icons/scim-python.png',
					  'credit':'GPL',
					  'languages':'zh',
					  'valid_input_chars':'abcdefghijklmnopqrstuvwxyz',
					  'max_key_length':'4',
			#		  'commit_keys':'space',
			#		  'forward_keys':'Return',
			#		  'select_keys':'1,2,3,4,5,6,7,8,9,0',
			#		  'page_up_keys':'Page_Up,minus',
			#		  'page_down_keys':'Page_Down,equal',
					  'status_prompt':'CN',
					  'def_full_width_punct':'TRUE',
					  'def_full_width_letter':'FALSE',
					  'user_can_define_phrase':'FALSE',
					  'pinyin_mode':'FALSE',
					  'rules':''}
					  #'rules':'ce2:p11+p12+p21+p22;ce3:p11+p21+p22+p31;ca4:p11+p21+p31+p41'}
			# inital the attribute in ime table, which should be updated from mabiao
			for _name in ime_keys:
				sqlstr = 'INSERT INTO main.ime (attr,val) VALUES (?,?);'
				self.db.execute( sqlstr, (_name,ime_keys[_name]) )
		# share variables in this class:
		self._mlen = int ( self.get_ime_property ("max_key_length") )
		#(MLEN, CLEN, M0, M1, M2, M3, M4, PHRASE, FREQ, USER_FREQ) = range (0,10)
		self._pt_index = ['mlen','clen']
		for i in range(self._mlen):
			self._pt_index.append ('m%d' %i)
		self._pt_index += ['phrase','freq','user_freq']
		self.user_can_define_phrase = self.get_ime_property('user_can_define_phrase')
		if self.user_can_define_phrase:
			if self.user_can_define_phrase.lower() == u'true' :
				self.user_can_define_phrase = True
			else:
				self.user_can_define_phrase = False
		else:
			print 'Could not find "user_can_define_phrase" entry from database, is it a outdated database?'
			self.user_can_define_phrase = False
		self.rules = self.get_rules ()

		
		# user database:
		if user_db != None:
			home_path = os.getenv ("HOME")
			tables_path = path.join (home_path, ".ibus",  "tables")
			user_db = path.join (tables_path, user_db)
			if not path.isdir (tables_path):
				os.makedirs (tables_path)
			try:
				desc = self.get_database_desc (user_db)
				if desc == None :
					self.init_user_db (user_db)
				elif desc["version"] != "0.1":
					new_name = "%s.%d" %(user_db, os.getpid())
					print >> sys.stderr, "Can not support the user db. We will rename it to %s" % new_name
					os.rename (user_db, new_name)
					self.init_user_db (user_db)
			except:
				import traceback
				traceback.print_exc()
		else:
			user_db = ":memory:"
		
		# open user phrase database
		try:
			self.db.execute ('ATTACH DATABASE "%s" AS user_db;' % user_db)
		except:
			print >> sys.stderr, "The user database was damaged. We will recreate it!"
			os.rename (user_db, "%s.%d" % (user_db, os.getpid ()))
			self.init_user_db (user_db)
			self.db.execute ('ATTACH DATABASE "%s" AS user_db;' % user_db)

		# try create all tables in user database
		self.create_tables ("user_db")
		self.create_indexes ("user_db")
		self.generate_userdb_desc ()
		
		# attach mudb for working process
		mudb = ":memory:"  
		self.db.execute ('ATTACH DATABASE "%s" AS mudb;' % mudb )
		self.create_tables ("mudb")
	
	def update_phrase (self, entry, database='user_db'):
		'''update'''
		#print entry
		_con = [ entry[-1] ] + list(entry[0:2+entry[0]]) + [entry[-3]]
		#print _con
		_condition = u''.join( map(lambda x: 'AND m%d = ? ' % x, range(entry[0]) )	)
		#print _condition
		sqlstr = 'UPDATE %s.phrases SET user_freq = ? WHERE mlen = ? AND clen = ? %s AND phrase = ?;' % (database, _condition)
		#print sqlstr
		self.db.execute ( sqlstr , _con )
		self.db.commit()

	def sync_usrdb (self):
		# we need to update the user_db
		#print 'sync userdb'
		mudata = self.db.execute ('SELECT * FROM mudb.phrases;').fetchall()
		data_u = filter ( lambda x: x[-2]==1, mudata)
		data_a = filter ( lambda x: x[-2]==2, mudata)
		data_n = filter ( lambda x: x[-2]==-1, mudata)
		#print data_a
		data_a = map (lambda x: (u''.join ( map(self.deparse, x[2:2+x[0]])),x[-3],0,x[-1] ), data_a)
		data_n = map (lambda x: (u''.join ( map(self.deparse, x[2:2+x[0]])),x[-3],-1,x[-1] ), data_n)
		#print data_u
		map (self.update_phrase, data_u)
		#print self.db.execute('select * from user_db.phrases;').fetchall()
		map (self.u_add_phrase,data_a)
		map (self.u_add_phrase,data_n)

	def create_tables (self, database):
		'''Create tables that contain all phrase'''

		try:
			self.db.execute( 'PRAGMA cache_size = 20000; ' )
			# increase the cache size to speedup sqlite enquiry
		except:
			pass
		if database == 'main':
			# create  ikeys table
			sqlstr = 'CREATE TABLE IF NOT EXISTS %s.ikeys (ikey TEXT PRIMARY KEY, id INTEGER);' % database
			self.db.execute ( sqlstr )
		
			# create goucima table, this table is used in construct new phrases
			sqlstr = 'CREATE TABLE IF NOT EXISTS %s.goucima (zi TEXT PRIMARY KEY' % database
			#for i in range(self._mlen):
			#	sqlstr += ', g%d INTEGER' % i 
			sqlstr += ''.join(map (lambda x: ', g%d INTEGER' % x, range(self._mlen)) )
			sqlstr += ');'
			self.db.execute ( sqlstr )

			# create pinyin table, this table is used in search single character for user handly
			sqlstr = 'CREATE TABLE IF NOT EXISTS %s.pinyin ( plen INTEGER, ' % database
			#for i in range(6):
			#	sqlstr += 'p%d INTEGER, ' % i 
			sqlstr += ''.join( map (lambda x: 'p%d INTEGER, ' % x, range(6) ) )
			sqlstr += 'zi TEXT, freq INTEGER);'
			self.db.execute ( sqlstr )

		# create phrase table (mabiao)
		sqlstr = 'CREATE TABLE IF NOT EXISTS %s.phrases ( mlen INTEGER, clen INTEGER, ' % database
		#for i in range(self._mlen):
		#	sqlstr += 'm%d INTEGER, ' % i 
		sqlstr += ''.join ( map (lambda x: 'm%d INTEGER, ' % x, range(self._mlen)) )
		sqlstr += 'phrase TEXT, freq INTEGER, user_freq INTEGER);'
		self.db.execute ( sqlstr )
		self.db.commit()
	
	def update_ime (self, attrs):
		'''Update attributes in ime table, attrs is a iterable object
		Like [(attr,val), (attr,val), ...]
		'''
		sqlstr = 'UPDATE main.ime SET val = ? WHERE attr = ?;' 
		for attr,val in attrs:
			_sqlstr = 'SELECT * from main.ime WHERE attr = ?' 
			res = self.db.execute( _sqlstr, (attr,) ).fetchall()
			if res:
				self.db.execute(sqlstr,(val,attr))
			else:
				#print '"',attr,'"'," didn't in ime property now!"
				pass
		# we need to update some self variables now.
		self._mlen = int (self.get_ime_property ('max_key_length' ))
		self._pt_index = ['mlen','clen']
		for i in range(self._mlen):
			self._pt_index.append ('m%d' %i)
		self._pt_index += ['phrase','freq','user_freq']
		self.user_can_define_phrase = self.get_ime_property('user_can_define_phrase')
		if self.user_can_define_phrase:
			if self.user_can_define_phrase.lower() == u'true' :
				self.user_can_define_phrase = True
			else:
				self.user_can_define_phrase = False
		else:
			print 'Could not find "user_can_define_phrase" entry from database, is it a outdated database?'
			self.user_can_define_phrase = False
		self.rules = self.get_rules ()

		#self.db.commit()

	def get_rules (self):
		'''Get phrase construct rules'''
		rules={'above':4}
		if self.user_can_define_phrase:
			try:
				_rules = self.get_ime_property ('rules')
				if _rules:
					_rules = _rules.strip().split(';')
				for rule in _rules:
					res = patt_r.match (rule)
					if res:
						cms = []
						if res.group(1) == 'a':
							rules['above'] = int(res.group(2))
						_cms = res.group(3).split('+')
						if len(_cms) > int(self.get_ime_property('max_key_length')):
							print 'rule: "%s" over max key length' % rule
							break
						for _cm in _cms:
							cm_res = patt_p.match(_cm)
							cms.append(( int(cm_res.group(1)),int(cm_res.group(2)) ))
						rules[int(res.group(2))]=cms
					else:
						print 'not a legal rule: "%s"'  % rule 
			except Exception:
				import traceback
				traceback.print_exc ()
			return rules
		else:
			return ""

	def add_phrases (self, phrases, database = 'main'):
		'''Add phrases to database, phrases is a iterable object
		Like: [(tabkeys, phrase, freq ,user_freq), (tabkeys, phrase, freq, user_freq), ...]
		'''
		if database == 'main':
			map (self.add_phrase, phrases)
		else:
			for phrase in phrases:
				self.add_phrase ( phrase, database )
		#self.db.commit()	
	
	def u_add_phrase (self,nphrase):
		'''Add a phrase to userdb'''
		self.add_phrase (nphrase,database='user_db')

	def add_phrase (self, aphrase, database = 'main'):
		'''Add phrase to database, phrase is a object of
		(tabkeys, phrase, freq ,user_freq)
		'''
		sqlstr = 'INSERT INTO %s.phrases ( mlen, clen, '
		sql_suffix = 'VALUES ( ?, ?, '
		mmlen = range(self._mlen)
		sqlstr += ''.join ( map(lambda x: 'm%d, ' %x , mmlen) )
		sql_suffix += ''.join ( map (lambda x: '?, ' , mmlen) )   
		sqlstr += 'phrase, freq, user_freq) '
		sql_suffix += '?, ?, ? );'
		sqlstr += sql_suffix
		
		tabkeys,phrase,freq,user_freq = aphrase
		try:
			tbks = self.parse(tabkeys)
			if len(tbks) != len(tabkeys):
				print 'In %s %s: we parse tabkeys fail' % (phrase, tabkeys )
				return
			record = [None, None, None, None, None]
			map( lambda x: record.append(None), range(self._mlen))
			record [0] = len (tabkeys)
			record [1] = len (phrase)
			record [2: 2+len(tabkeys)] = map (lambda x: tbks[x].get_key_id(), range(0,len(tabkeys)))
			record [2+self._mlen] = phrase
			record [2+self._mlen+1] = freq
			record [2+self._mlen+2] = user_freq
			self.db.execute (sqlstr % database, record)
		except Exception:
			import traceback
			traceback.print_exc()
		#if database != 'mudb':
		self.db.commit()	

	def add_goucima (self, gcms):
		'''Add goucima into database, gcms is iterable object
		Like gcms = [(zi,goucima),(zi,goucima), ...]
		'''
		count = 1
		for zi,gcm in gcms:
			_con = ''
			_val = ''
			_len = min ( len(gcm),self._mlen)
			for i in range( _len ):
				_con += ', g%d' % i
				_val += ', ?' 
			sqlstr = '''INSERT INTO main.goucima ( zi %s )
			VALUES ( ? %s );''' % (_con, _val)
			try:
				gc = self.parse(gcm)
				if len(gc) != len(gcm):
					error_m = u'%s %s: Can not parse goucima' % (zi, gcm )
					raise Exception ( error_m.encode ('utf8') )
				record = [zi]
				for i in range(_len):
					record.append( gc[i].get_key_id())
				self.db.execute (sqlstr , record)
			
			except Exception:
				import traceback
				traceback.print_exc()
			count += 1
		self.db.commit()

	def add_pinyin (self, pinyins, database = 'main'):
		'''Add pinyin to database, pinyins is a iterable object
		Like: [(zi,pinyin, freq), (zi, pinyin, freq), ...]
		'''
		sqlstr = 'INSERT INTO %s.pinyin ( plen, '
		sql_suffix = 'VALUES ( ?, '
		for i in range(6):
			sqlstr += 'p%d, ' % i
			sql_suffix += '?, '
		sqlstr += 'zi, freq ) '
		sql_suffix += '?, ? );'
		sqlstr += sql_suffix
		
		count = 1
		for pinyin,zi,freq in pinyins:
			try:
				py = self.parse(pinyin)
				if len(py) != len(pinyin):
					error_m = u'%s %s: Can not parse pinyin' % (zi, pinyin )
					raise Exception ( error_m.encode ('utf8') )
				record = [None, None, None, None, None, None, None, None, None]
				record [0] = len (pinyin)
				for i in range(0,len(pinyin)):
					record [ 1+i ] = py[i].get_key_id()
				record [-2] = zi
				record [-1] = freq
				self.db.execute (sqlstr % database, record)
			except Exception:
				print count, ': ', zi.encode('utf8'), ' ', pinyin
				import traceback
				traceback.print_exc()
			count += 1

		self.db.commit()	
	
	def optimize_database (self, database='main'):
		sqlstr = '''
			CREATE TABLE tmp AS SELECT * FROM %(database)s.phrases;
			DELETE FROM %(database)s.phrases;
			INSERT INTO %(database)s.phrases SELECT * FROM tmp ORDER BY %(tabkeystr)s mlen ASC, freq DESC;
			DROP TABLE tmp;
			CREATE TABLE tmp AS SELECT * FROM %(database)s.goucima;
			DELETE FROM %(database)s.goucima;
			INSERT INTO %(database)s.goucima SELECT * FROM tmp ORDER BY zi,g0,g1;
			DROP TABLE tmp;
			CREATE TABLE tmp AS SELECT * FROM %(database)s.pinyin;
			DELETE FROM %(database)s.pinyin;
			INSERT INTO %(database)s.pinyin SELECT * FROM tmp ORDER BY p0,p1,p2,p3,p4,p5,plen ASC;
			DROP TABLE tmp;
			'''
		tabkeystr = ''
		for i in range(self._mlen):
			tabkeystr +='m%d, ' % i
		self.db.executescript (sqlstr % {'database':database,'tabkeystr':tabkeystr })
		self.db.executescript ("VACUUM;")
		self.db.commit()
	
	def create_indexes(self, database):
		sqlstr = '''
			DROP INDEX IF EXISTS %(database)s.goucima_index_z;
			CREATE INDEX IF NOT EXISTS %(database)s.goucima_index_z ON goucima (zi,g0,g1);
			DROP INDEX IF EXISTS %(database)s.pinyin_index_i;
			CREATE INDEX IF NOT EXISTS %(database)s.pinyin_index_i ON pinyin (p0,p1,p2,p3,p4,p5,plen ASC, freq DESC);
			VACUUM; 
			''' % { 'database':database }

		sqlstr_t = '''
			DROP INDEX IF EXISTS %(database)s.phrases_index_p;
			CREATE INDEX IF NOT EXISTS %(database)s.phrases_index_p ON phrases (%(tabkeystr)s mlen ASC, freq DESC);
			DROP INDEX IF EXISTS %(database)s.phrases_index_i;
			CREATE INDEX IF NOT EXISTS %(database)s.phrases_index_i ON phrases (phrase, mlen ASC);
			''' 
		tabkeystr = ''
		for i in range(self._mlen):
			tabkeystr +='m%d,' % i
		if database == 'main':
			sqlstr = sqlstr_t % {'database':database,'tabkeystr':tabkeystr } + sqlstr
		else:
			sqlstr = sqlstr_t % {'database':database,'tabkeystr':tabkeystr }
		self.db.executescript (sqlstr)
		self.db.commit()
	
	def compare (self,x,y):
		return cmp (x[0],y[0]) or -(cmp (x[-1],y[-1])) or -(cmp (x[-2],y[-2]))

	def select_words( self, tabkeys ):
		'''
		Get phrases from database by XingMa_Key objects
		( which should be equal or less than the max key length)
		This method is called in XingMa by passing UserInput held data
		Return result[:] 
		'''
		# firstly, we make sure the len we used is equal or less than the max key length
		_len = min( len(tabkeys),self._mlen )
		_condition = ''
		_condition += ''.join ( map (lambda x: 'AND m%d = ? ' %x, range(_len) ) )
		# you can increase the x in _len + x to include more result, but in the most case, we only need one more key result, so we don't need the extra overhead :)
		# we start search for 1 key more, if nothing, then 2 key more and so on
		# this is the max len we need to add into the select cause.
		w_len = self._mlen - _len +1
		# we start from 2, because it is < in the sqlite select, which need 1 more.
		x_len = 2
		while x_len <= w_len + 1:
			sqlstr = '''SELECT * FROM (SELECT * FROM main.phrases WHERE mlen < %(mk)d  %(condition)s 
			UNION ALL
			SELECT * FROM user_db.phrases WHERE mlen < %(mk)d %(condition)s 
			UNION ALL
			SELECT * FROM mudb.phrases WHERE mlen < %(mk)d %(condition)s )
			ORDER BY mlen ASC, user_freq DESC, freq DESC;''' % { 'mk':_len+x_len, 'condition':_condition}
			# we have redefine the __int__(self) in class tabdict.tab_key to return the key id, so we can use map to got key id :)
			_tabkeys = map(int,tabkeys[:_len])
			_tabkeys += _tabkeys + _tabkeys
			result = self.db.execute(sqlstr, _tabkeys).fetchall()
			#self.db.commit()
			# if we find word, we stop this while, 
			if len(result) >0:
				break
			x_len += 1
		# here in order to get high speed, I use complicated map
		# to subtitute for
		sysdb={}
		usrdb={}
		mudb={}
		_cand = []
		#searchres = map ( lambda res: res[-2] and [ True, [(res[:-2],[res[:-1],res[-1:]])] ]\
		#		or [ False, [(res[:-2] , [res[:-1],res[-1:]])] ] \
		#		, result )
		searchres = map ( lambda res: [ bool(res[-2]), bool(res[-1]), [(res[:-2],[res[:-1],res[-1:]])] ], result)
		# for sysdb
		reslist=filter( lambda x: x[0] and (not x[1]), searchres )
		map (lambda x: sysdb.update(x[2]), reslist)
		# for usrdb
		reslist=filter( lambda x: (not x[0]) and x[1], searchres )
		map (lambda x: usrdb.update(x[2]), reslist)
		# for mudb
		reslist=filter( lambda x: x[0] and x[1], searchres )
		map (lambda x: mudb.update(x[2]), reslist)

		# first process mudb
		searchres = map ( lambda key: mudb[key][0] + mudb[key][1], mudb )
		#print searchres
		map (_cand.append, searchres)

		# now process usrdb and sysdb
		searchres = map ( lambda key:  (not mudb.has_key(key))  and usrdb[key][0] + usrdb[key][1]\
				or None , usrdb )
		searchres = filter(lambda x: bool(x), searchres )
		#print searchres
		map (_cand.append, searchres)
		searchres = map ( lambda key: ((not mudb.has_key(key)) and (not usrdb.has_key(key)) )and sysdb[key][0] + sysdb[key][1]\
				or None, sysdb )
		searchres = filter (lambda x: bool(x), searchres)
		map (_cand.append, searchres)
		#for key in usrdb:
		#	if not sysdb.has_key (key):
		#		_cand.append( usrdb[key][0] + usrdb[key][1] )
		#	else:
		#		_cand.append( sysdb[key][0] + usrdb[key][1] )
		#for key in sysdb:
		#	if not usrdb.has_key (key):
		#		_cand.append( sysdb[key][0] + sysdb[key][1] )
		_cand.sort(cmp=self.compare)
		return _cand[:]

	def select_zi( self, tabkeys ):
		'''
		Get zi from database by XingMa_Key objects
		( which should be equal or less than 6)
		This method is called in XingMa by passing UserInput held data
		Return  result[:] 
		'''
		# firstly, we make sure the len we used is equal or less than the max pinyin length 6
		_len = min( len(tabkeys), 6 )
		_condition = ''
		#for i in range(_len):
		#	_condition += 'AND p%d = ? ' % i
		_condition += ''.join ( map (lambda x: 'AND p%d = ? ' %x, range(_len)) )
		# you can increase the x in _len + x to include more result, but in the most case, we only need one more key result, so we don't need the extra overhead :)
		sqlstr = '''SELECT * FROM main.pinyin WHERE plen < %(mk)d  %(condition)s 
		ORDER BY plen ASC, freq DESC;''' % { 'mk':_len+2, 'condition':_condition}
		# we have redefine the __int__(self) in class tabdict.tab_key to return the key id, so we can use map to got key id :)
		_tabkeys = map(int,tabkeys[:_len])
		result = self.db.execute(sqlstr, _tabkeys).fetchall()
		#self.db.commit()
		return result[:]

	def get_ime_property( self, attr ):
		'''get IME property from database, attr is the string of property,
		which should be str.lower() :)
		'''
		sqlstr = 'SELECT val FROM main.ime WHERE attr = ?' 
		_result = self.db.execute( sqlstr, (attr,)).fetchall()
		#self.db.commit()
		if _result:
			return _result[0][0]
		else:
			return None

	def get_phrase_table_index (self):
		'''get a list of phrase table columns name'''
		return self._pt_index[:]

	def generate_userdb_desc (self):
		try:
			sqlstring = 'CREATE TABLE IF NOT EXISTS user_db.desc (name PRIMARY KEY, value);'
			self.db.executescript (sqlstring)
			sqlstring = 'INSERT OR IGNORE INTO user_db.desc  VALUES (?, ?);'
			self.db.execute (sqlstring, ('version', '0.1'))
			self.db.execute (sqlstring, ('id', str(uuid.uuid4 ())))
			sqlstring = 'INSERT OR IGNORE INTO user_db.desc  VALUES (?, DATETIME("now", "localtime"));'
			self.db.execute (sqlstring, ("create-time", ))
			self.db.commit ()
		except:
			import traceback
			traceback.print_exc ()

	def init_user_db (self,db_file):
		if not path.exists (db_file):
			db = sqlite3.connect (db_file)
			db.execute('PRAGMA page_size = 4096;')
			db.execute( 'PRAGMA cache_size = 20000;' )
			db.execute( 'PRAGMA temp_store = MEMORY; ' )
			db.execute( 'PRAGMA synchronous = OFF; ' )
			db.commit()
	
	def get_database_desc (self, db_file):
		if not path.exists (db_file):
			return None
		try:
			db = sqlite3.connect (db_file)
			db.execute('PRAGMA page_size = 4096;')
			db.execute( 'PRAGMA cache_size = 20000;' )
			db.execute( 'PRAGMA temp_store = MEMORY; ' )
			db.execute( 'PRAGMA synchronous = OFF; ' )
			desc = {}
			for row in db.execute ("SELECT * FROM desc;").fetchall():
				desc [row[0]] = row[1]
			self.db.commit()
			return desc
		except:
			return None
	
	def get_gcm_id (self, zi):
		'''Get goucima of given character'''
		sqlstr = 'SELECT g0,g1 FROM main.goucima WHERE zi =?;'
		return self.db.execute(sqlstr,(zi,)).fetchall()[0]

	def parse_phrase (self, phrase):
		'''Parse phrase to get its XingMa code'''
		# first we make sure that we are parsing unicode string
		try:
			phrase = unicode(phrase)
		except:
			phrase = phrase.decode('utf8')
		p_len = len(phrase) 
		tabkeylist = []
		if p_len < 2:
			# phrase should not be shorter than 2
			return []
		try:
			if p_len >= self.rules['above']:
				rule = self.rules[ self.rules['above'] ]
			elif p_len in self.rules:
				rule = self.rules[p_len]
			else:
				raise Exception ('unsupport len of phrase')
			if len(rule) > self._mlen:
				raise Exception ('fault rule: %s' % rule)
			#for (zi,ma) in rule:
			#	if zi > 0:
			#		zi -= 1
			#	gcm = self.get_gcm_id (phrase[zi])
			#	tabkeylist.append(gcm[ma-1])
			tabkeylist = map (lambda x: self.get_gcm_id ( phrase[x[0]-1] )[ x[1]-1 ], rule )
			return [len( tabkeylist)] + [p_len]  + tabkeylist[:] + [phrase]

		except Exception:
			import traceback
			traceback.print_exc ()

	def parse_phrase_to_tabkeys (self,phrase):
		'''Get the XingMa encoding of the phrase in string form'''
		tabres = self.parse_phrase (phrase) [2:-1]
		tabkeys= u''.join ( map(self.deparse, tabres) )
		return tabkeys

	def check_phrase (self,phrase,tabkey=None):
		# if IME didn't support user define phrase,
		# we divide user input phrase into characters,
		# and then check its frequence
		if type(phrase) != type(u''):
			phrase = phrase.decode('utf8')
		if self.user_can_define_phrase:
			self.check_phrase_internal (phrase, tabkey)
		else:
			map(self.check_phrase_internal, phrase, tabkey)
	
	def check_phrase_internal (self,phrase,tabkey=None):
		'''Check word freq and user_freq
		'''
		if type(phrase) != type(u''):
			phrase = phrase.decode('utf8')
		if len(phrase) >=2:
			wordattr = self.parse_phrase ( phrase )
			_len = len (wordattr) -3
		if tabkey == None:
			sqlstr = '''SELECT * FROM (SELECT * FROM main.phrases WHERE phrase = ?
			UNION ALL SELECT * FROM user_db.phrases WHERE phrase = ?
			UNION ALL SELECT * FROM mudb.phrases WHERE phrase = ?)
			ORDER BY user_freq DESC, freq DESC
			''' 
			result = self.db.execute(sqlstr, (phrase,phrase,phrase)).fetchall()
		else:
			sqlstr = '''SELECT * FROM (SELECT * FROM main.phrases WHERE phrase = ?
			UNION ALL SELECT * FROM user_db.phrases WHERE phrase = ?
			UNION ALL SELECT * FROM mudb.phrases WHERE phrase = ?)
			ORDER BY user_freq DESC, freq DESC
			''' 
			result = self.db.execute(sqlstr, (phrase,phrase,phrase)).fetchall()

		sysdb = {}
		usrdb = {}
		mudb = {}
		searchres = map ( lambda res: [ bool(res[-2]), bool(res[-1]), [(res[:-2],[res[:-1],res[-1]])] ], result)
		# for sysdb
		reslist=filter( lambda x: x[0] and (not x[1]), searchres )
		map (lambda x: sysdb.update(x[2]), reslist)
		# for usrdb
		reslist=filter( lambda x: (not x[0]) and x[1], searchres )
		map (lambda x: usrdb.update(x[2]), reslist)
		# for mudb
		reslist=filter( lambda x: x[0] and x[1], searchres )
		map (lambda x: mudb.update(x[2]), reslist)
		
		tabkey = ''
		if len(phrase) >=2:
			tabkey = u''.join ( map(self.deparse,wordattr[2:2+_len]) )
			#for k in wordattr[2:2+_len]:
			#	tabkey += self.deparse (k)
		
		sqlstr = 'UPDATE mudb.phrases SET user_freq = ? WHERE mlen = ? AND clen = ? %s AND phrase = ?;'
		
		try:
			if len(phrase) == 1:
				# this is a character
				# we remove the keys contained in mudb from usrdb
				keyout = filter (lambda k: mudb.has_key(k), usrdb.keys() )
				map (usrdb.pop, keyout)
				# we remove the keys contained in mudb and usrdb from sysdb
				keyout = filter (lambda k: mudb.has_key(k) or usrdb.has_key(k) , sysdb.keys() )
				map (sysdb.pop, keyout)
				# first mudb
				map (lambda res: self.db.execute ( sqlstr % ''.join( map(lambda x: 'AND m%d = ? ' % x, range(res[0])) ) ,  [ mudb[res][1] + 1 ] + list( res[:2+res[0]]) + list (res[2+self._mlen:]) ) , mudb.keys())
				# -----original for loop of above map: 
				#for res in mudb.keys ():
				#	_con = [ mudb[res][1] + 1 ] + list( res[:2+res[0]]) + list (res[2+self._mlen:])
				#	_condition = ''.join( map(lambda x: 'AND m%d = ? ' % x, range(res[0])) )	
				#	self.db.execute ( sqlstr % _condition, _con )
				
				# then usrdb
				map ( lambda res: self.add_phrase ( (''.join ( map(self.deparse,res[2:2+int(res[0])] ) ),phrase,1,usrdb[res][1]+1  ), database = 'mudb') , usrdb.keys() )				
				# -----original for loop of above map: 
				#for res in usrdb.keys ():
				#	#if mudb.has_key (res):
				#	#	continue
				#	tabkey = ''.join ( map(self.deparse,res[2:2+int(res[0])] ) )
				#	# here we use freq 1 to denote the phrase needed update in user_db
				#	self.add_phrase ((tabkey,phrase,1,usrdb[res][1]+1 ), database = 'mudb')
				# last sysdb
				map ( lambda res: self.add_phrase ( ( ''.join ( map(self.deparse,res[2:2+int(res[0])]) ),phrase,2,1 ), database = 'mudb'), sysdb.keys() )
				# -----original for loop of above map: 
				#for res in sysdb.keys ():
				#	tabkey = ''.join ( map(self.deparse,res[2:2+int(res[0])]) )
				#	# here we use freq 2 to denote the word needed addition to user_db
				#	self.add_phrase ((tabkey,phrase,2,1), database = 'mudb')
			else:
				# this is a phrase
				if len (result) == 0 and self.user_can_define_phrase:
					# this is a new phrase, we add it into user_db
					self.add_phrase ( (tabkey,phrase,-1,1), database = 'mudb')
				elif len (result) > 0:
					# we remove the keys contained in mudb from usrdb
					keyout = filter (lambda k: mudb.has_key(k), usrdb.keys() )
					map (usrdb.pop, keyout)
					# we remove the keys contained in mudb and usrdb from sysdb
					keyout = filter (lambda k: mudb.has_key(k) or usrdb.has_key(k) , sysdb.keys() )
					map (sysdb.pop, keyout)
					
					# first we process mudb
					# the original for loop can be found above in 'len==1'
					map (lambda res: self.db.execute ( sqlstr % ''.join( map(lambda x: 'AND m%d = ? ' % x, range(res[0])) ) ,  [ mudb[res][1] + 1 ] + list( res[:2+res[0]]) + list (res[2+self._mlen:]) ) , mudb.keys())
					# then usrdb
					map ( lambda res: self.add_phrase ( (''.join ( map(self.deparse,res[2:2+int(res[0])] ) ),phrase,1,usrdb[res][1]+1  ), database = 'mudb') , usrdb.keys() )				
					# last sysdb
					map ( lambda res: self.add_phrase ( ( ''.join ( map(self.deparse,res[2:2+int(res[0])]) ),phrase,2,1 ), database = 'mudb'), sysdb.keys() )

				else:
					# we come to here when the ime dosen't support user phrase define
					pass
			
			self.db.commit()
		except:
			import traceback
			traceback.print_exc ()

	def find_zi_code (self,zi):
		'''Check word freq and user_freq
		'''
		zi = zi.decode('utf8')
		sqlstr = '''SELECT * FROM main.phrases WHERE phrase = ?
		ORDER BY mlen ASC;
''' 
		result = self.db.execute(sqlstr, (zi,)).fetchall()
		#self.db.commit()
		codes = []
		try:
			if result:
				for _res in result:
					tabkey = u''
					for i in range ( int ( _res[0] ) ):
						tabkey += self.deparse ( _res[2+i] )
					codes.append(tabkey)
		except:
			import traceback
			traceback.print_exc ()
		return codes[:]

	def remove_phrase (self,phrase,database='user_db'):
		'''Remove phrase from database, default is from user_db
		phrase should be the a row of select * result from database
		Like (mlen,clen,m0,m1,m2,m3,phrase,freq,user_freq)
		'''
		_ph = list(phrase[:-2])
		_condition = ''	
		for i in range(_ph[0]):
			_condition += 'AND m%d = ? ' % i
		nn =_ph.count(None)
		if nn:
			for i in range(nn):
				_ph.remove(None)
		msqlstr= 'SELECT * FROM %(database)s.phrases WHERE mlen = ? and clen = ? %(condition)s AND phrase = ? ;' % { 'database':database, 'condition':_condition }
		if self.db.execute(msqlstr, _ph).fetchall():
			sqlstr = 'DELETE FROM %(database)s.phrases WHERE mlen = ? AND clen =? %(condition)s AND phrase = ?  ;' % { 'database':database, 'condition':_condition }
			self.db.execute(sqlstr,_ph)

		msqlstr= 'SELECT * FROM mudb.phrases WHERE mlen = ? and clen = ? %(condition)s AND phrase = ? ;' % { 'condition':_condition }
		if self.db.execute(msqlstr, _ph).fetchall():
			sqlstr = 'DELETE FROM mudb.phrases WHERE mlen = ? AND clen =? %(condition)s AND phrase = ?  ;' % {  'condition':_condition }
			self.db.execute(sqlstr,_ph)

		self.db.commit()